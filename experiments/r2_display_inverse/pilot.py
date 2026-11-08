#!/usr/bin/env python3
"""Small frozen R2 grid; saves model-only outcomes, never clinical results."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from inverse import evaluate, write_results


def execute(out: Path, size: int = 64, maxiter: int = 90) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for pupil in (3.0, 4.0):
        for delta in (-0.45, 0.45):
            label = f"pupil_{pupil:.1f}_delta_{delta:+.2f}"
            summary, images = evaluate(pupil_mm=pupil, delta_D=delta, n=size,
                                       maxiter=maxiter)
            write_results(out / label, summary, images)
            row = {"case": label, "pupil_mm": pupil, "delta_D": delta,
                   "unmodified_rel_l2": summary["metrics"]["unmodified"]["retinal_image_rel_l2"],
                   "shared_rel_l2": summary["metrics"]["shared"]["retinal_image_rel_l2"],
                   "rgb_rel_l2": summary["metrics"]["rgb"]["retinal_image_rel_l2"],
                   "rgb_8bit_rel_l2": summary["metrics"]["rgb"]["retinal_image_8bit_gamma22_rel_l2"],
                   "rgb_gamma_2_0_rel_l2": summary["metrics"]["rgb"]["gamma_mismatch_rel_l2"]["2.0"],
                   "rgb_gamma_2_4_rel_l2": summary["metrics"]["rgb"]["gamma_mismatch_rel_l2"]["2.4"],
                   "rgb_clipped_fraction": summary["metrics"]["rgb"]["clipped_pixels_fraction"],
                   "optimizer_success": summary["optimizer"]["rgb"]["optimizer_success"],
                   "interpretation": "SIMULATED_IMAGE_FIT_NOT_EYE_ACCOMMODATION"}
            rows.append(row)
    with (out / "pilot.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out / "pilot_summary.json").write_text(json.dumps({
        "rows": len(rows),
        "complete": all(r["optimizer_success"] for r in rows),
        "scope": "SIMULATION_ONLY",
        "optical_calibration": "NONE",
        "human_accommodation": "NOT_MEASURED",
        "therapeutic_effect": "NOT_MEASURED",
        "non_independent_model_evaluation": True,
        "comparisons": "unmodified vs shared-gray optimization vs per-channel RGB optimization",
        "note": "Three RGB fields have greater capacity than one gray field; this is a model-fit comparison, not biological evidence.",
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--size", type=int, default=64)
    p.add_argument("--maxiter", type=int, default=90)
    args = p.parse_args()
    rows = execute(args.out, size=args.size, maxiter=args.maxiter)
    for row in rows:
        print(json.dumps(row, sort_keys=True))


if __name__ == "__main__":
    main()
