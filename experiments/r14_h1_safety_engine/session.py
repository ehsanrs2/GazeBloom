#!/usr/bin/env python3
"""R14 deterministic *simulation-only* H1 session safety core.

This is NOT an authorized participant display engine. No stimuli, camera,
GUI, network, user data or human approvals are loaded here. The state
machine is for bounded timing, permanent stop, response order and
missingness testing before a separate ethically reviewed H1 protocol.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import PurePosixPath
import re

STUDY = "GAZEBLOOM_R14_SIMULATED_H1_SAFETY_ENGINE_V1"
STATES = frozenset({"READY", "VIEWING", "RESPONSE", "REST", "FINISHED", "STOPPED"})
CODE = re.compile(r"^[0-9a-f]{64}$")
WORDS = frozenset({"NOVA", "LUMA", "MIRA", "TORA"})
VIEW_S = 10.0
REST_S = 30.0


class SessionViolation(ValueError):
    """An unsafe transition, clock order, or malformed session plan."""


def validate_binding(rows: list[dict]) -> None:
    """Validate the R13 mapping shape without interpreting study approval."""
    required = {"trial_id", "condition_code", "word", "image_relative_path",
                "image_sha256", "max_view_seconds", "min_rest_seconds"}
    if len(rows) != 8:
        raise SessionViolation("exactly eight trial mappings are required")
    if {r.get("word") for r in rows} != WORDS:
        raise SessionViolation("exactly four predetermined word scenes required")
    for i, r in enumerate(rows):
        if set(r) != required or r["trial_id"] != f"T{i+1:02d}":
            raise SessionViolation("R13 mapping fields / trial ID mismatch")
        if (r["condition_code"] not in ("X", "Y")
                or r["max_view_seconds"] != "10"
                or r["min_rest_seconds"] != "30"):
            raise SessionViolation("R10/R13 condition or frozen time limits modified")
        if not isinstance(r["image_sha256"], str) or not CODE.fullmatch(r["image_sha256"]):
            raise SessionViolation("each image requires a pinned SHA-256")
        p=PurePosixPath(r["image_relative_path"])
        if (p.is_absolute() or ".." in p.parts or len(p.parts) != 2
                or p.parts[0] != "UNAPPROVED_images"
                or p.suffix != ".png"):
            raise SessionViolation("unexpected R12 candidate-image relative path")
        if p.name != f"{i%4+1:02d}_unused.png":
            # The canonical word index is immutable in R12, while R13 shuffles
            # scene order across trials. Validate by the canonical name below.
            scene_index = ("NOVA", "LUMA", "MIRA", "TORA").index(r["word"])+1
            expected = f"{scene_index:02d}_{r['word']}_{r['condition_code']}.png"
            if p.name != expected:
                raise SessionViolation("candidate path does not match word and arm")
    for i in range(4):
        a,b=rows[i],rows[i+4]
        if a["word"] != b["word"] or a["condition_code"] == b["condition_code"]:
            raise SessionViolation("each word needs one X and one Y at trial lag four")


@dataclass(frozen=True)
class Snapshot:
    state: str
    trial_number: int
    planned_trials: int
    display_seconds_remaining: float
    rest_seconds_remaining: float
    stimulus_visible: bool
    stop_available: bool
    human_exposure_authorized: bool = False


class SimulatedSession:
    """No external I/O. All timestamps are caller-supplied monotonic seconds."""

    def __init__(self, binding: list[dict]):
        validate_binding(binding)
        self._binding = [dict(row) for row in binding]
        self.state = "READY"
        self.current = 0
        self.deadline: float | None = None
        self._last_time: float | None = None
        self.rows: list[dict] = []
        self.event_log: list[dict] = []

    def _time(self, now: float) -> float:
        if (not isinstance(now, (int,float)) or isinstance(now, bool)
                or not math.isfinite(now) or now < 0
                or (self._last_time is not None and now < self._last_time)):
            raise SessionViolation("event clock must be finite, nonnegative and monotonic")
        self._last_time = float(now)
        return float(now)

    def _log(self, now: float, event: str) -> None:
        self.event_log.append({
            "time_seconds_simulated": now,
            "event": event,
            "state_after": self.state,
            "trial_number": self.current + 1 if self.current < 8 else None,
        })

    def start(self, now: float) -> None:
        now = self._time(now)
        if self.state != "READY":
            raise SessionViolation("trial starts only by explicit action from READY")
        self.state = "VIEWING"
        self.deadline = now + VIEW_S
        self._log(now, "manual_start_simulated")

    def tick(self, now: float) -> None:
        now = self._time(now)
        if self.state == "VIEWING" and self.deadline is not None and now >= self.deadline:
            self.state = "RESPONSE"
            self.deadline = None
            self._log(now, "end_virtual_view_hide_placeholder")
        elif self.state == "REST" and self.deadline is not None and now >= self.deadline:
            self.state = "READY"
            self.deadline = None
            self._log(now, "rest_complete_manual_next_required")

    def record_response(self, now: float, *, clarity: float | None = None,
                        comfort: float | None = None, reading_correct: bool | None = None,
                        discomfort: bool = False) -> None:
        now=self._time(now)
        if self.state != "RESPONSE":
            raise SessionViolation("responses allowed only after image has been hidden")
        if not isinstance(discomfort, bool):
            raise SessionViolation("discomfort must be boolean")
        if discomfort:
            self._permanent_stop(now, reason="discomfort_reported")
            return
        for name, value in (("clarity",clarity),("comfort",comfort)):
            if (not isinstance(value, (int,float)) or isinstance(value,bool)
                    or not math.isfinite(value) or not 0 <= value <= 10):
                raise SessionViolation(f"{name} must be finite from 0 to 10")
        if reading_correct is not None and not isinstance(reading_correct,bool):
            raise SessionViolation("reading_correct must be boolean or omitted")
        row=self._binding[self.current]
        self.rows.append({
            "trial_id":row["trial_id"],
            "clarity_0_10":str(clarity),
            "comfort_0_10":str(comfort),
            "reading_correct":"" if reading_correct is None else str(int(reading_correct)),
            "discomfort_flag":"0",
            "stopped":"0",
        })
        self.current += 1
        if self.current >= 8:
            self.state = "FINISHED"
            self.deadline = None
            self._log(now, "synthetic_completion")
        else:
            self.state = "REST"
            self.deadline = now + REST_S
            self._log(now, "start_virtual_rest")

    def _permanent_stop(self, now: float, *, reason: str) -> None:
        if self.state in ("STOPPED","FINISHED"):
            return
        if self.state in ("VIEWING","RESPONSE"):
            row=self._binding[self.current]
            self.rows.append({
                "trial_id":row["trial_id"],"clarity_0_10":"",
                "comfort_0_10":"","reading_correct":"",
                "discomfort_flag":"1" if reason=="discomfort_reported" else "0",
                "stopped":"1",
            })
        self.state = "STOPPED"
        self.deadline = None
        self._log(now, "permanent_stop_"+reason)

    def stop(self, now: float) -> None:
        """Irreversible, hides simulated stimulus; never permits resume."""
        now = self._time(now)
        self._permanent_stop(now, reason="operator_stop")

    def snapshot(self, now: float) -> Snapshot:
        self.tick(now)
        remain_view=max(0.,self.deadline-now) if self.state=="VIEWING" else 0.
        remain_rest=max(0.,self.deadline-now) if self.state=="REST" else 0.
        return Snapshot(
            state=self.state,trial_number=min(self.current+1,8),
            planned_trials=8,display_seconds_remaining=remain_view,
            rest_seconds_remaining=remain_rest,
            stimulus_visible=False,  # NEVER emit actual stimulus in R14
            stop_available=self.state not in ("STOPPED","FINISHED"),
        )

    def report(self) -> dict:
        return {
            "study":STUDY,"mode":"SYNTHETIC_NO_HUMANS",
            "terminal_state":self.state,
            "completed_simulated_trials":sum(row["stopped"]=="0" for row in self.rows),
            "stopped_simulated_trials":sum(row["stopped"]=="1" for row in self.rows),
            "planned_trials":8,"response_rows":len(self.rows),
            "remaining_not_observed_trials":8-len(self.rows),
            "camera_used":False,"participant_data_collected":False,
            "stimulus_images_displayed":False,"human_exposure_authorized":False,
            "measured_human_accommodation":False,
            "safety_note":"Simulation of timing/stop logic is not verified real-world safety",
        }
