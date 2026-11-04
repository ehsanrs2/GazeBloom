"""Pure monotonic-clock reminder state machine, independent of desktop UI.

Caller supplies monotonic timestamps. No thread, polling, disk or OS access
occurs here. A "completed" break is explicitly user-confirmed, never inferred
from elapsed time. Active screen time is deliberately NOT measured.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class State(str, Enum):
    STOPPED = "stopped"
    WORKING = "working"
    PROMPT = "prompt"
    BREAK = "break"
    BREAK_READY = "break_ready"
    PAUSED = "paused"


class TransitionError(ValueError):
    """Action is not valid in the current state."""


@dataclass(frozen=True)
class Settings:
    interval_seconds: float = 20 * 60
    break_seconds: float = 20
    snooze_seconds: float = 5 * 60

    def __post_init__(self) -> None:
        for key in ("interval_seconds", "break_seconds", "snooze_seconds"):
            value = getattr(self, key)
            if not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
                raise ValueError(f"{key} must be finite and positive")


class BreakTimer:
    """A single-session, user-controlled break reminder.

    Contract:
      * The caller MUST supply nondecreasing monotonic timestamps.
      * next_due is a monotonic deadline, never a wall-clock timestamp.
      * Pause/resume preserve the remaining countdown.
      * No overdue reminders are caught up in a burst.
      * Deadline expiry does not certify that a break happened.
    """

    def __init__(self, settings: Settings = Settings()) -> None:
        self.settings = settings
        self.state = State.STOPPED
        self.deadline: float | None = None
        self._paused_from: State | None = None
        self._remaining: float | None = None
        self._last_now: float | None = None
        self._events: list[dict] = []
        self._prompt_delivered = False

    def _time(self, now: float) -> float:
        if not isinstance(now, (int, float)) or not isfinite(now):
            raise ValueError("now must be finite")
        if self._last_now is not None and now < self._last_now:
            raise ValueError("monotonic time moved backwards")
        self._last_now = float(now)
        return float(now)

    def _emit(self, event: str, *, source: str = "app") -> None:
        self._events.append({"event_type": event, "state": self.state.value, "source": source})

    def take_events(self) -> list[dict]:
        """Return and clear pending events. Disabled logging means no persistence."""
        result, self._events = self._events, []
        return result

    def start(self, now: float) -> None:
        now = self._time(now)
        if self.state != State.STOPPED:
            raise TransitionError("session is already active")
        self._paused_from = None
        self._remaining = None
        self._prompt_delivered = False
        self.state = State.WORKING
        self.deadline = now + self.settings.interval_seconds
        self._emit("session_started", source="user")

    def advance(self, now: float) -> None:
        now = self._time(now)
        if self.state == State.WORKING and self.deadline is not None and now >= self.deadline:
            self.state, self.deadline = State.PROMPT, None
            self._prompt_delivered = False
            self._emit("reminder_due")
        elif self.state == State.BREAK and self.deadline is not None and now >= self.deadline:
            self.state, self.deadline = State.BREAK_READY, None
            self._emit("break_target_elapsed")

    def delivered(self, now: float) -> None:
        self._time(now)
        if self.state != State.PROMPT:
            raise TransitionError("no reminder to deliver")
        if not self._prompt_delivered:
            self._prompt_delivered = True
            self._emit("reminder_delivered", source="ui")

    def snooze(self, now: float) -> None:
        now = self._time(now)
        if self.state != State.PROMPT:
            raise TransitionError("snooze requires a reminder")
        self.state = State.WORKING
        self.deadline = now + self.settings.snooze_seconds
        self._emit("reminder_snoozed", source="user")

    def skip(self, now: float) -> None:
        now = self._time(now)
        if self.state != State.PROMPT:
            raise TransitionError("skip requires a reminder")
        self.state = State.WORKING
        self.deadline = now + self.settings.interval_seconds
        self._emit("break_skipped", source="user")

    def begin_break(self, now: float) -> None:
        now = self._time(now)
        if self.state not in (State.WORKING, State.PROMPT):
            raise TransitionError("cannot start a break here")
        self.state = State.BREAK
        self.deadline = now + self.settings.break_seconds
        self._emit("break_started", source="user")

    def complete_break(self, now: float) -> None:
        self.advance(now)
        if self.state != State.BREAK_READY:
            raise TransitionError("break target has not elapsed")
        self.state = State.WORKING
        self.deadline = now + self.settings.interval_seconds
        self._emit("break_completed", source="user_confirmed")

    def interrupt_break(self, now: float) -> None:
        now = self._time(now)
        if self.state not in (State.BREAK, State.BREAK_READY):
            raise TransitionError("no break to interrupt")
        self.state = State.WORKING
        self.deadline = now + self.settings.interval_seconds
        self._emit("break_interrupted", source="user")

    def pause(self, now: float) -> None:
        now = self._time(now)
        if self.state in (State.STOPPED, State.PAUSED):
            raise TransitionError("cannot pause here")
        self._paused_from = self.state
        self._remaining = max(0.0, self.deadline - now) if self.deadline is not None else None
        self.deadline = None
        self.state = State.PAUSED
        self._emit("paused", source="user")

    def resume(self, now: float) -> None:
        now = self._time(now)
        if self.state != State.PAUSED or self._paused_from is None:
            raise TransitionError("not paused")
        restored = self._paused_from
        self.state = restored
        self.deadline = now + self._remaining if self._remaining is not None else None
        self._paused_from = self._remaining = None
        self._emit("resumed", source="user")

    def clock_gap(self, now: float) -> None:
        """App detected a large wall/monotonic discrepancy (e.g. sleep).

        Avoid an unexpected prompt after wake, and require explicit resume.
        Timezone changes are presentation-only and never drive deadlines.
        """
        now = self._time(now)
        if self.state in (State.STOPPED, State.PAUSED):
            return
        self.pause(now)
        self._emit("clock_gap_detected", source="runtime")

    def stop(self, now: float) -> None:
        self._time(now)
        if self.state == State.STOPPED:
            return
        self.state = State.STOPPED
        self.deadline = None
        self._paused_from = self._remaining = None
        self._emit("session_ended", source="user")

    def remaining_seconds(self, now: float) -> float | None:
        """Pure, non-mutating display helper; no tick or event emitted."""
        if self.state == State.PAUSED:
            return self._remaining
        if self.deadline is None:
            return None
        return max(0.0, self.deadline - now)
