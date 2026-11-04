"""Small manual-control Tk desktop adapter; no camera, idle spying or telemetry.

Uses standard library Tkinter. In-app notices and optional Linux notify-send
are best-effort. This is not a system-wide screen-time tracker.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time

from .activity import IdleGate, IdleWatcher, LinuxIdleProbe
from .engine import BreakTimer, Settings, State, TransitionError
from .eventlog import LocalEventLog


def maybe_notify() -> None:
    """Non-blocking best-effort Linux notification, never a hard dependency."""
    if sys.platform.startswith("linux") and shutil.which("notify-send"):
        try:
            subprocess.Popen(
                ["notify-send", "--app-name=GazeBloom", "Time for a screen break",
                 "Look away from the screen at something about 6 metres away."],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            pass


def launch(
    interval_min: int = 20,
    log_path: str | None = None,
    *,
    idle_aware: bool = False,
    idle_threshold_sec: int = 60,
) -> None:
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError as exc:
        raise RuntimeError(
            "Tkinter is unavailable for the selected Python: "
            f"{sys.executable}. On Ubuntu, install python3-tk and select "
            "the matching interpreter with: "
            "uv sync --python /usr/bin/python3 --no-managed-python; "
            "uv run --python /usr/bin/python3 --no-managed-python "
            "python -m gazebloom. See docs/UV_SETUP_FA.md."
        ) from exc

    if not 1 <= interval_min <= 120:
        raise ValueError("interval must be between 1 and 120 minutes")

    engine = BreakTimer(Settings(interval_seconds=interval_min * 60))
    logger = LocalEventLog(log_path, interval_seconds=interval_min * 60, break_seconds=20) if log_path else None
    idle_gate = IdleGate(threshold_seconds=idle_threshold_sec)
    idle_watcher = IdleWatcher(LinuxIdleProbe()) if idle_aware else None
    root = tk.Tk()
    root.title("GazeBloom — Gentle screen breaks")
    root.geometry("525x415")
    root.minsize(425, 395)
    frame = ttk.Frame(root, padding=20)
    frame.pack(expand=True, fill="both")
    heading = ttk.Label(frame, text="GazeBloom", font=("", 20, "bold"))
    heading.pack(pady=(0, 5))
    state_line = ttk.Label(frame, text="Stopped")
    state_line.pack(pady=5)
    activity_line = ttk.Label(frame, text=(
        "Activity detection initializing (opt-in)" if idle_watcher
        else "Activity detection off (manual timer)"
    ))
    activity_line.pack(pady=2)
    countdown = ttk.Label(frame, text="—", font=("", 24))
    countdown.pack(pady=6)
    advice = ttk.Label(frame, wraplength=475, justify="center",
                       text="Start a session. Timings are reminders, not medical treatment.")
    advice.pack(pady=(2, 14))
    actions = ttk.Frame(frame)
    actions.pack(fill="x")
    controls: dict[str, ttk.Button] = {}

    def flush() -> None:
        events = engine.take_events()
        if logger is not None:
            try:
                logger.record(events)
            except OSError as exc:
                advice.config(text=f"Could not write opt-in event log: {exc}")
        for event in events:
            if event["event_type"] == "reminder_due":
                maybe_notify()

    def act(name: str) -> None:
        now = time.monotonic()
        try:
            if name == "start":
                idle_gate.manual_override()
                engine.start(now)
            elif name == "pause":
                idle_gate.manual_override()
                if engine.state == State.PAUSED:
                    engine.resume(now)
                else:
                    engine.pause(now)
            elif name == "break":
                engine.begin_break(now)
            elif name == "done":
                engine.complete_break(now)
            elif name == "snooze":
                engine.snooze(now)
            elif name == "skip":
                engine.skip(now)
            elif name == "interrupt":
                engine.interrupt_break(now)
            elif name == "stop":
                idle_gate.manual_override()
                engine.stop(now)
        except (TransitionError, ValueError) as exc:
            advice.config(text=str(exc))
        flush()
        render(now)

    for i, (name, label) in enumerate([
        ("start", "Start"), ("pause", "Pause / Resume"), ("break", "Take a break"),
        ("done", "Confirm break"), ("snooze", "Snooze 5 min"),
        ("skip", "Skip"), ("interrupt", "End early"), ("stop", "Stop"),
    ]):
        btn = ttk.Button(actions, text=label, command=lambda key=name: act(key))
        btn.grid(row=i // 2, column=i % 2, padx=4, pady=4, sticky="ew")
        controls[name] = btn
    actions.columnconfigure(0, weight=1)
    actions.columnconfigure(1, weight=1)

    footer = ttk.Label(
        frame,
        text=("Local events saved by explicit --log opt-in." if logger else
              "No data recording. No camera or eye tracking."),
        foreground="gray",
        wraplength=475,
    )
    footer.pack(side="bottom", pady=5)

    def render(now: float) -> None:
        state = engine.state
        state_line.config(text=state.value.replace("_", " ").title())
        remaining = engine.remaining_seconds(now)
        if remaining is not None:
            seconds = int(math.ceil(remaining))
            minutes, remainder = divmod(seconds, 60)
            countdown.config(text=f"{minutes:02d}:{remainder:02d}")
        else:
            countdown.config(text="—")
        if state == State.WORKING:
            advice.config(text="Continue normally; an optional reminder appears when due.")
        elif state == State.PROMPT:
            advice.config(text="Look away from this screen at a real distant object (≈6 m). "
                               "Start your 20-second break, snooze or skip.")
        elif state == State.BREAK:
            advice.config(text="Look away from the screen. Return after the timer has elapsed. "
                               "The app cannot verify where you looked.")
        elif state == State.BREAK_READY:
            advice.config(text="If you took the break, confirm it. Otherwise choose End early.")
        elif state == State.PAUSED:
            advice.config(text="Paused. Choose Pause / Resume to continue.")
        elif state == State.STOPPED:
            advice.config(text="Start a session. You control all reminders and breaks.")
        enabled = {
            "start": state == State.STOPPED,
            "pause": state not in (State.STOPPED,),
            "break": state in (State.WORKING, State.PROMPT),
            "done": state == State.BREAK_READY,
            "snooze": state == State.PROMPT,
            "skip": state == State.PROMPT,
            "interrupt": state in (State.BREAK, State.BREAK_READY),
            "stop": state != State.STOPPED,
        }
        for name, button in controls.items():
            button.configure(state="normal" if enabled[name] else "disabled")
        controls["pause"].configure(text=("Resume" if state == State.PAUSED else "Pause"))

    last_mono = time.monotonic()
    last_wall = time.time()
    if idle_watcher is not None:
        idle_watcher.start()

    def tick() -> None:
        nonlocal last_mono, last_wall
        now, wall = time.monotonic(), time.time()
        wall_diff, mono_diff = wall - last_wall, now - last_mono
        last_mono, last_wall = now, wall
        # Conservative signal, not proof of sleep: also triggered by big clock changes.
        if abs(wall_diff - mono_diff) > 8:
            # No auto-resume after an abnormal time discontinuity.
            idle_gate.manual_override()
            engine.clock_gap(now)
        else:
            if idle_watcher is not None:
                sample = idle_watcher.latest()
                if sample is None or now - sample.observed_monotonic > 8:
                    idle_gate.observe(None, now, engine)
                else:
                    idle_gate.observe(sample.idle_seconds, now, engine)
            engine.advance(now)
        if idle_watcher is not None:
            if idle_gate.status == "away":
                activity_line.config(text="Away detected — work countdown held")
            elif idle_gate.status == "active":
                activity_line.config(text="Recent keyboard/mouse activity detected (not eye gaze)")
            else:
                activity_line.config(text="Idle status unavailable — ordinary timer active")
        if engine.state == State.PROMPT:
            engine.delivered(now)
        flush()
        render(now)
        root.after(500, tick)

    def close() -> None:
        if idle_watcher is not None:
            idle_watcher.stop()
        engine.stop(time.monotonic())
        flush()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    render(time.monotonic())
    root.after(500, tick)
    root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description="GazeBloom desktop screen-break reminder")
    parser.add_argument("--interval-min", type=int, default=20,
                        help="reminder interval in minutes (1..120, default 20)")
    parser.add_argument("--log", type=Path, default=None,
                        help="OPT IN: append event-only JSONL to this local file")
    parser.add_argument("--idle-aware", action="store_true",
                        help="OPT IN: hold work countdown when Linux input is idle")
    parser.add_argument("--idle-threshold-sec", type=int, default=60,
                        help="absence of keyboard/mouse input before holding countdown (15..3600)")
    args = parser.parse_args()
    if not 15 <= args.idle_threshold_sec <= 3600:
        parser.error("--idle-threshold-sec must be between 15 and 3600")
    if not args.idle_aware and args.idle_threshold_sec != 60:
        parser.error("--idle-threshold-sec requires --idle-aware")
    launch(
        args.interval_min,
        str(args.log) if args.log is not None else None,
        idle_aware=args.idle_aware,
        idle_threshold_sec=args.idle_threshold_sec,
    )


if __name__ == "__main__":
    main()
