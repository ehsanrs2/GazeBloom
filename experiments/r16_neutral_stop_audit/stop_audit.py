#!/usr/bin/env python3
"""R16 neutral-only GUI STOP dispatch audit, never a participant/image runner.

Measurements end after a Tk label update and update_idletasks(), NOT when
monitor photons change. No participant exposure, camera, image imports or
experimental stimuli. No safety latency threshold is inferred from these data.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import statistics
import time
from typing import Callable

STUDY = "GAZEBLOOM_R16_NEUTRAL_ONLY_STOP_DISPATCH_V1"


@dataclass(frozen=True)
class StopResult:
    state: str
    source: str
    dispatch_ms: float | None
    neutralize_callback_succeeded: bool


class StopLatch:
    """Pure, irreversible STOP gate. The caller owns real GUI rendering."""

    def __init__(self, neutralize: Callable[[], None], clock: Callable[[], float] = time.perf_counter):
        self._neutralize = neutralize
        self._clock = clock
        self.state = "READY"
        self.last_result: StopResult | None = None

    def start_placeholder(self) -> None:
        if self.state != "READY":
            raise ValueError("placeholder may start only once and never after STOP")
        self.state = "PLACEHOLDER"

    def stop(self, source: str) -> StopResult:
        if source not in ("button", "escape", "close", "synthetic"):
            raise ValueError("unrecognized STOP source")
        if self.last_result is not None:
            return self.last_result
        # Fail closed before the display callback, including on callback error.
        self.state = "STOPPED"
        began = self._clock()
        if not isinstance(began, (int, float)) or not math.isfinite(began):
            self.last_result = StopResult("STOPPED", source, None, False)
            raise ValueError("invalid monotonic clock")
        try:
            self._neutralize()
        except Exception:
            self.last_result = StopResult("STOPPED", source, None, False)
            raise
        ended = self._clock()
        if not isinstance(ended, (int, float)) or not math.isfinite(ended) or ended < began:
            self.last_result = StopResult("STOPPED", source, None, False)
            raise ValueError("clock moved backwards or became invalid")
        self.last_result = StopResult("STOPPED", source, (ended - began) * 1000, True)
        return self.last_result


def summary(results: list[StopResult], *, environment: str) -> dict:
    if not results or any(not x.neutralize_callback_succeeded or x.dispatch_ms is None
                          or not math.isfinite(x.dispatch_ms) or x.dispatch_ms < 0
                          or x.state != "STOPPED" for x in results):
        raise ValueError("only complete neutral callback dispatches can be summarized")
    times = [x.dispatch_ms for x in results if x.dispatch_ms is not None]
    return {
        "study": STUDY, "environment": environment, "sample_count": len(times),
        "dispatch_ms_min": min(times), "dispatch_ms_median": statistics.median(times),
        "dispatch_ms_max": max(times),
        "measured_endpoint": "Python STOP entry to Tk update_idletasks return",
        "NOT_measured": ["physical_pixel_suppression", "monitor_scanout",
                         "human_reaction_time", "ocular_accommodation"],
        "actual_pngs_opened": 0, "camera_recordings": 0, "human_participants": 0,
        "human_exposure_authorized": False,
        "h1_runner_available": False,
        "threshold_certification": False,
    }


def tk_smoke(samples: int, *, operator_demo: bool = False) -> dict:
    if not 1 <= samples <= 100:
        raise ValueError("samples must be in 1..100")
    import tkinter as tk

    root = tk.Tk()
    root.title("R16 NEUTRAL-ONLY OPERATOR AUDIT — NO PARTICIPANTS")
    root.geometry("640x230")
    root.configure(bg="#292929")
    banner = tk.Label(root, text="NO IMAGES / NO HUMAN STUDY", fg="white", bg="#292929")
    banner.pack(pady=10)
    surface = tk.Label(root, text="NEUTRAL PLACEHOLDER", bg="#777777", fg="white",
                       width=55, height=4)
    surface.pack(pady=6)
    root.update_idletasks()
    results: list[StopResult] = []

    def neutralize() -> None:
        surface.configure(text="STOPPED — BLANK NEUTRAL PLACEHOLDER", bg="#555555")
        root.update_idletasks()

    def run_one(source: str) -> None:
        latch = StopLatch(neutralize)
        latch.start_placeholder()
        results.append(latch.stop(source))

    if operator_demo:
        latch = StopLatch(neutralize)
        latch.start_placeholder()
        button = tk.Button(root, text="STOP NOW (Esc)", command=lambda: latch.stop("button"))
        button.pack(pady=8)
        root.bind("<Escape>", lambda _event: latch.stop("escape"))
        def on_close() -> None:
            latch.stop("close")
            root.destroy()
        root.protocol("WM_DELETE_WINDOW", on_close)
        root.mainloop()
        if latch.last_result is None:
            raise RuntimeError("operator demo closed without STOP")
        results.append(latch.last_result)
        environment = "LOCAL_OPERATOR_TK_NEUTRAL_ONLY"
    else:
        # Synthetic invocation, NOT a physical keypress or elapsed human response.
        for _ in range(samples):
            surface.configure(text="NEUTRAL PLACEHOLDER", bg="#777777")
            root.update_idletasks()
            run_one("synthetic")
        root.destroy()
        environment = "CI_TK_SYNTHETIC_CALLBACK"
    return summary(results, environment=environment)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--ci-smoke", action="store_true", help="synthetic Tk callback loop only")
    modes.add_argument("--operator-demo", action="store_true", help="neutral GUI, no research images")
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = tk_smoke(args.samples, operator_demo=args.operator_demo)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        # Write-once output: never overwrite an earlier operator report.
        with args.out.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
