"""One-shot neutral gray patch bench. No image, camera, sensor or participant I/O."""
from __future__ import annotations

import argparse
import json
import time

NEUTRAL = "#555555"
ACTIVE = "#999999"
MAX_ARM_MS = 15000


class Bench:
    def __init__(self, root, tk):
        self.root = root
        self.state = "READY"
        self.result = None
        self.timer = None
        root.title("R18 neutral display bench — NOT H1")
        root.geometry("640x420")
        root.resizable(False, False)
        self.status = tk.Label(root, text="READY — neutral patch; no research images")
        self.status.pack(pady=8)
        self.patch = tk.Frame(root, width=420, height=240, bg=NEUTRAL,
                              bd=0, highlightthickness=0)
        self.patch.pack(pady=8)
        self.arm_button = tk.Button(root, text="ARM once", command=self.arm)
        self.arm_button.pack(side="left", padx=30)
        tk.Button(root, text="STOP (Esc)", command=lambda: self.stop("button")).pack(side="right", padx=30)
        root.bind("<Escape>", lambda event: self.stop("escape"))
        root.protocol("WM_DELETE_WINDOW", self.close)

    def arm(self):
        if self.state != "READY":
            return False
        self.state = "ARMED"
        self.arm_button.configure(state="disabled")
        self.patch.configure(bg=ACTIVE)
        self.status.configure(text="ARMED — stop with Esc; timeout 15 s")
        self.timer = self.root.after(MAX_ARM_MS, lambda: self.stop("timeout"))
        return True

    def stop(self, source):
        if self.state == "STOPPED":
            return self.result
        was_armed = self.state == "ARMED"
        self.state = "STOPPED"
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        start = time.perf_counter_ns()
        self.patch.configure(bg=NEUTRAL)
        self.arm_button.configure(state="disabled")
        self.status.configure(text=f"STOPPED — {source}; restart requires a new process")
        self.root.update_idletasks()
        self.result = {"mode": "NEUTRAL_BENCH_SOFTWARE_ONLY", "stop_source": source,
                       "armed_before_stop": was_armed,
                       "tk_dispatch_ms": (time.perf_counter_ns()-start)/1e6,
                       "physical_display_measured": False, "human_exposure_authorized": False}
        return self.result

    def close(self):
        self.stop("close")
        self.root.destroy()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--operator-bench", action="store_true")
    mode.add_argument("--ci-smoke", action="store_true")
    args = p.parse_args()
    import tkinter as tk
    root = tk.Tk()
    bench = Bench(root, tk)
    if args.ci_smoke:
        root.update_idletasks()
        assert bench.patch.cget("bg") == NEUTRAL
        assert bench.arm()
        assert bench.patch.cget("bg") == ACTIVE
        result = bench.stop("synthetic")
        assert bench.patch.cget("bg") == NEUTRAL and not bench.arm()
        assert bench.stop("synthetic") == result
        root.destroy()
    else:
        root.mainloop()
    print(json.dumps(bench.result, sort_keys=True))


if __name__ == "__main__":
    main()
