"""Optional idle-awareness for Linux desktops.

Input inactivity is only a proxy for presence, NOT a measure of screen gaze.
GNOME Mutter exposes GetIdletime over the user's session bus; X11 can fall
back to xprintidle if installed. No remote telemetry or input event capture.
Queries run on a daemon worker to avoid blocking the Tk main thread.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from math import isfinite
from typing import Callable, Mapping

from .engine import BreakTimer, State


def parse_idle_milliseconds(output: str) -> int | None:
    """Parse strict gdbus '(uint64 123,)' or xprintidle '123' output."""
    value = output.strip()
    match = re.fullmatch(r"(?:\(\s*(?:uint64\s+)?(\d+)\s*,?\s*\)|(\d+))", value)
    if not match:
        return None
    count = int(match.group(1) or match.group(2))
    # Reject implausible sentinel values and malformed service responses.
    return count if 0 <= count <= 86_400_000 else None


@dataclass(frozen=True)
class IdleReading:
    idle_seconds: float | None
    backend: str
    observed_monotonic: float


class LinuxIdleProbe:
    """Query only the current session; fails as 'unknown' on unsupported DEs.

    No probing outside Linux, no shell evaluation, no privileges required.
    """

    def __init__(
        self,
        *,
        environ: Mapping[str, str] | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        which: Callable[[str], str | None] = shutil.which,
    ) -> None:
        self.environ = dict(os.environ if environ is None else environ)
        self.runner = runner
        self.which = which

    def _run(self, argv: list[str]) -> int | None:
        try:
            result = self.runner(argv, check=False, capture_output=True, text=True, timeout=0.75)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return None
        return parse_idle_milliseconds(result.stdout) if result.returncode == 0 else None

    def read(self) -> tuple[float | None, str]:
        desktop = self.environ.get("XDG_CURRENT_DESKTOP", "").upper()
        session_type = self.environ.get("XDG_SESSION_TYPE", "").lower()
        if "GNOME" in desktop and self.which("gdbus"):
            milliseconds = self._run([
                "gdbus", "call", "--session",
                "--dest", "org.gnome.Mutter.IdleMonitor",
                "--object-path", "/org/gnome/Mutter/IdleMonitor/Core",
                "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime",
            ])
            if milliseconds is not None:
                return milliseconds / 1000.0, "gnome-mutter"
        # X11 utility does not interrogate the real Wayland user session.
        if session_type == "x11" and self.which("xprintidle"):
            milliseconds = self._run(["xprintidle"])
            if milliseconds is not None:
                return milliseconds / 1000.0, "x11-xprintidle"
        return None, "unavailable"


class IdleWatcher:
    """Bounded-rate worker; the GUI reads samples but never blocks on D-Bus."""

    def __init__(self, probe: LinuxIdleProbe, *, poll_seconds: float = 2.0) -> None:
        if not isfinite(poll_seconds) or poll_seconds <= 0:
            raise ValueError("poll_seconds must be finite and positive")
        self.probe = probe
        self.poll_seconds = poll_seconds
        self._closed = threading.Event()
        self._queue: queue.Queue[IdleReading] = queue.Queue(maxsize=1)
        self._thread: threading.Thread | None = None
        self._last: IdleReading | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("IdleWatcher already started")
        self._thread = threading.Thread(target=self._run, name="gazebloom-idle", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._closed.is_set():
            try:
                seconds, backend = self.probe.read()
            except Exception:  # Backend failures must never crash the UI.
                seconds, backend = None, "unavailable"
            sample = IdleReading(seconds, backend, time.monotonic())
            try:
                self._queue.put_nowait(sample)
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._queue.put_nowait(sample)
                except queue.Full:
                    pass
            self._closed.wait(self.poll_seconds)

    def latest(self) -> IdleReading | None:
        try:
            while True:
                self._last = self._queue.get_nowait()
        except queue.Empty:
            return self._last

    def stop(self) -> None:
        self._closed.set()


class IdleGate:
    """Automatically hold active reminders only on a reliable idle reading.

    Ownership matters: an auto-resume must never override a *manual* pause.
    Unknown observations do not auto-pause or auto-resume.
    User-selected breaks continue ticking while keyboard/mouse are idle.
    """

    def __init__(self, *, threshold_seconds: float = 60.0) -> None:
        if not isfinite(threshold_seconds) or not 15 <= threshold_seconds <= 3600:
            raise ValueError("threshold_seconds must be 15..3600")
        self.threshold_seconds = threshold_seconds
        self.auto_paused = False
        self.status = "unknown"

    def manual_override(self) -> None:
        self.auto_paused = False

    def observe(self, idle_seconds: float | None, now: float, engine: BreakTimer) -> None:
        if idle_seconds is None or not isfinite(idle_seconds) or idle_seconds < 0:
            self.status = "unknown"
            return

        if idle_seconds >= self.threshold_seconds:
            self.status = "away"
            if engine.state in (State.WORKING, State.PROMPT):
                engine.pause(now, source="idle_monitor")
                self.auto_paused = True
        else:
            self.status = "active"
            if self.auto_paused:
                if engine.state == State.PAUSED:
                    engine.resume(now, source="idle_monitor")
                self.auto_paused = False
