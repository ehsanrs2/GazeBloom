#!/usr/bin/env python3
"""R3: preregistered synthetic stress grid for R2 image-specific optimization.

Targets in each stress profile are simulated by the alternative forward model;
they are NOT acquired retinal images. This experiment tests model mismatch,
not measured accommodation, safety, or eye-strain treatment.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
from statistics import median

import numpy as np

R2_PATH = Path(__file__).resolve().parents[1] / "r2_display_inverse"
sys.path.insert(0, str(R2_PATH))
from inverse import (optical_otfs, optimize_display, forward,
                     scene_pattern)  # noqa: E402
from alt_optics import (code_to_light, mix_channels, optical_forward,
                        optics_otfs, relative_l2, validation_profiles)  # noqa: E402

FROZEN_SCENES = ("original_texture", "synthetic_letter_edges")
FROZEN_DELTAS = (-0.45, 0.45)
VERSION = "R3_ALTERNATE_SURROGATE_STRESS_V1"


def make_scene(name: str, n: int) -> np.ndarray:
    if name == "original_texture":
        return scene_pattern(n, seed=812)
    if name == "synthetic_letter_edges":
        y, x = np.indices((n, n))
        background = np.full((n, n), .72)
        # deterministic high-contrast bars and a checker region, not real text
        strokes = (
            ((x > n // 7) & (x < n // 7 + 4) & (y > n // 6) & (y < 5*n // 6))
            | ((y > n // 6) & (y < n // 6 + 4) & (x > n // 7) & (x < n // 2))
            | ((x > n // 2) & (x < n // 2 + 4) & (y > n // 6) & (y < 5*n // 6))
            | ((y > 5*n // 6 - 4) & (y < 5*n // 6) & (x > n // 2) & (x < 6*n // 7))
        )
        background[strokes] = .12
        pattern = ((x // 5 + y // 5) % 2).astype(bool)
        region = (x > n // 2) & (y < n // 3)
        background[region & pattern] = .40
        return background
    raise ValueError(f"unknown frozen scene: {name}")


def evaluate_profile(
    source: np.ndarray, alternatives: dict[str, np.ndarray],
    delta: float, profile, *, image_size: int,
) -> dict[str, float]:
    base_otfs, target_otfs = optics_otfs(profile, delta, image_size)
    source_rgb = np.broadcast_to(source, (3,) + source.shape)
    # Reference is an idealized distant scene seen through the *profile's*
    # target optics. It is NOT a display-generated or measured eye target.
    target = mix_channels(
        optical_forward(source_rgb, target_otfs), profile.channel_leakage
    )
    metrics = {}
    for name, display in alternatives.items():
        decoded = code_to_light(display, profile.gamma_actual)
        prediction = mix_channels(
            optical_forward(decoded, base_otfs), profile.channel_leakage
        )
        metrics[name] = relative_l2(prediction, target)
    return metrics


def run(pupil_mm: float = 4., image_size: int = 64,
        maxiter: int = 90) -> tuple[list[dict], dict]:
    if pupil_mm != 4.:
        # This first protocol is frozen to a single nominal fitting pupil.
        raise ValueError("R3 v1 nominal fitting pupil fixed at 4mm")
    profiles = validation_profiles()
    rows = []
    fit_status = []
    for scene_name in FROZEN_SCENES:
        source = make_scene(scene_name, image_size)
        source_rgb = np.broadcast_to(source, (3,) + source.shape)
        for delta in FROZEN_DELTAS:
            # The *same* R2 model is used only for training, never the
            # alternate forward optics below. R2 has more RGB parameters.
            r2_base, r2_target = optical_otfs(
                pupil_mm, delta, size=image_size
            )
            r2_target_image = forward(source_rgb, r2_target)
            gray, gray_status = optimize_display(
                r2_base, r2_target_image, source,
                shared=True, maxiter=maxiter
            )
            rgb, rgb_status = optimize_display(
                r2_base, r2_target_image, source,
                shared=False, maxiter=maxiter
            )
            fit_status.append({
                "scene": scene_name, "delta_D": delta,
                "gray_converged": gray_status["optimizer_success"],
                "rgb_converged": rgb_status["optimizer_success"],
                "gray_iterations": gray_status["iterations"],
                "rgb_iterations": rgb_status["iterations"],
            })
            alternatives = {
                "unmodified": source_rgb,
                "shared": gray,
                "rgb": rgb,
            }
            rgb_chroma = float(np.mean(np.abs(rgb - rgb.mean(axis=0, keepdims=True))))
            rgb_clipped = float(np.mean((rgb <= 1e-9) | (rgb >= 1 - 1e-9)))
            for profile in profiles:
                metrics = evaluate_profile(
                    source, alternatives, delta, profile,
                    image_size=image_size
                )
                rows.append({
                    "scene": scene_name, "delta_D": delta,
                    "profile": profile.name,
                    "unmodified_error": metrics["unmodified"],
                    "shared_error": metrics["shared"],
                    "rgb_error": metrics["rgb"],
                    "rgb_beats_shared": metrics["rgb"] < metrics["shared"],
                    "rgb_beats_unmodified": metrics["rgb"] < metrics["unmodified"],
                    "rgb_minus_shared": metrics["rgb"] - metrics["shared"],
                    "rgb_chroma_abs": rgb_chroma,
                    "rgb_clipped_fraction": rgb_clipped,
                    "scope": "ALTERNATE_SIMULATOR_ONLY_NO_HUMAN_DATA",
                })
    gains = [r["shared_error"] - r["rgb_error"] for r in rows]
    winners = sum(r["rgb_beats_shared"] for r in rows)
    summary = {
        "study": VERSION,
        "n_scenes": len(FROZEN_SCENES),
        "n_directions": len(FROZEN_DELTAS),
        "n_profiles": len(profiles),
        "rows": len(rows),
        "profile_definitions": [p.__dict__ for p in profiles],
        "fitting_status": fit_status,
        "rgb_beats_shared_count": winners,
        "rgb_beats_unmodified_count": sum(r["rgb_beats_unmodified"] for r in rows),
        "median_shared_minus_rgb_error": median(gains),
        "min_shared_minus_rgb_error": min(gains),
        "max_shared_minus_rgb_error": max(gains),
        "all_optimizers_converged": all(
            v["gray_converged"] and v["rgb_converged"] for v in fit_status
        ),
        "robustness_gate": (
            "SYNTHETIC_STRESS_CASES_ALL_WIN_NO_PHYSICAL_VALIDATION"
            if winners == len(rows) else
            "SYNTHETIC_STRESS_CASES_NOT_ALL_WIN"
        ),
        "not_covered": [
            "measured display RGB spectra",
            "measured EOTF / ICC calibration",
            "real optical wavefront/PSF",
            "actual human accommodation",
            "retinal physiology and cone spectral sensitivities",
            "physical stimulus safety and clinical eye-strain outcomes",
            "generalization of one prefilter across unseen images",
        ],
        "conclusion_scope": "IN_SILICO_ONLY_NOT_INDEPENDENT_PHYSICAL_EVIDENCE",
    }
    return rows, summary


def write_results(out: Path, rows: list[dict], summary: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "stress.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out / "summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )
    here = Path(__file__).resolve().parent
    source_map = {
        "r2_inverse.py": here.parent / "r2_display_inverse" / "inverse.py",
        "r3_alt_optics.py": here / "alt_optics.py",
        "r3_runner.py": here / "evaluate.py",
    }
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest()
              for name, path in source_map.items()}
    manifest = {
        "study": VERSION, "hashes": hashes,
        "output_files": ["stress.csv", "summary.json", "manifest.json"],
        "seed": 812,
        "source": "R2 optimizer trained on monochromatic surrogate; R3 evaluation on alternative toy scalar pupil model",
        "original_target": "model-predicted hypothetical defocus target; no human or physical validation",
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--size", type=int, default=64)
    p.add_argument("--maxiter", type=int, default=90)
    args = p.parse_args()
    rows, summary = run(image_size=args.size, maxiter=args.maxiter)
    write_results(args.out, rows, summary)
    print(json.dumps({
        "study": VERSION, "rows": summary["rows"],
        "rgb_beats_shared_count": summary["rgb_beats_shared_count"],
        "median_shared_minus_rgb_error": summary["median_shared_minus_rgb_error"],
        "robustness_gate": summary["robustness_gate"],
        "scope": summary["conclusion_scope"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
