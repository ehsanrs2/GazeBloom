#!/usr/bin/env python3
"""R5: independently optimized 3HW RGB nulls for synthetic optical cue studies.

All fits use the exact same artificial target, image, objective, optimizer,
regularization, box bounds and number of free variables (3*H*W).
Only the training forward operator changes. R3 synthetic optics scores all
outputs without refitting. This is NOT a measured accommodation experiment.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import sys
from statistics import median

import numpy as np

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "r2_display_inverse"))
sys.path.insert(0, str(BASE / "r3_model_mismatch"))
sys.path.insert(0, str(BASE.parent))
sys.path.insert(0, str(BASE / "r4_directional_controls"))
from inverse import forward, optical_otfs, optimize_display  # noqa: E402
from alt_optics import (code_to_light, mix_channels, optical_forward, optics_otfs,
                        relative_l2, validation_profiles)  # noqa: E402
from experiments.r3_model_mismatch.evaluate import FROZEN_SCENES, make_scene  # noqa: E402
# Both R3 and R4 modules are named "evaluate"; use R4's score routine by
# importing a uniquely named compatibility module below (not shadowed).
from directional_metric import signed_alignment, artifact_proxy  # noqa: E402

STUDY = "R5_INDEPENDENT_EQUAL_PARAMETER_RGB_NULLS_V1"
SIGNS = (-0.45, 0.45)
MODELS = ("mapped_rgb", "permuted_fit_rgb", "achromatic_fit_rgb")
CONTROLS = MODELS + ("optimized_gray", "unmodified")
LAMBDA_DEVIATION = .002
LAMBDA_CHROMA = .01


def surrogate_operator(base_otfs: np.ndarray, hypothesis: str) -> np.ndarray:
    """Frozen hypotheses: correct R2 mapping; swapped R/B; no chromatic PSF."""
    if base_otfs.ndim != 3 or base_otfs.shape[0] != 3:
        raise ValueError("expected R/G/B OTFs")
    if hypothesis == "mapped_rgb":
        return base_otfs.copy()
    if hypothesis == "permuted_fit_rgb":
        return base_otfs[[2, 1, 0], ...].copy()
    if hypothesis == "achromatic_fit_rgb":
        return np.repeat(base_otfs.mean(axis=0, keepdims=True), 3, axis=0)
    raise ValueError(f"unknown hypothesis: {hypothesis}")


def fit_candidates(scene: np.ndarray, *, maxiter: int = 90) -> tuple[dict, list]:
    n = scene.shape[0]
    if scene.shape != (n, n) or n < 50 or n % 2 or maxiter <= 0:
        raise ValueError("requires even square >=50 scene and positive maxiter")
    initial = np.broadcast_to(scene, (3, n, n)).copy()
    fitted = {name: {} for name in CONTROLS}
    status = []
    for sign in SIGNS:
        nominal_base, nominal_target = optical_otfs(4., sign, size=n)
        # All candidate arms fit exactly the same target computed once,
        # not targets permuted or replaced for a favorable comparison.
        fixed_target = forward(initial, nominal_target)
        for arm in MODELS:
            observed = surrogate_operator(nominal_base, arm)
            rgb, info = optimize_display(
                observed, fixed_target, scene, shared=False,
                lambda_deviation=LAMBDA_DEVIATION,
                lambda_chroma=LAMBDA_CHROMA, maxiter=maxiter,
            )
            if rgb.shape != (3, n, n) or not np.isfinite(rgb).all():
                raise AssertionError("RGB candidate parameter or finiteness failure")
            fitted[arm][sign] = rgb
            status.append({
                "sign_D": sign, "arm": arm, "variables": 3*n*n,
                "success": info["optimizer_success"], "iterations": info["iterations"],
                "objective_in_training_model": info["objective"],
            })
        gray, info = optimize_display(
            nominal_base, fixed_target, scene, shared=True,
            lambda_deviation=LAMBDA_DEVIATION,
            lambda_chroma=LAMBDA_CHROMA, maxiter=maxiter,
        )
        fitted["optimized_gray"][sign] = gray
        fitted["unmodified"][sign] = initial
        status.append({"sign_D": sign, "arm": "optimized_gray",
                       "variables": n*n, "success": info["optimizer_success"],
                       "iterations": info["iterations"],
                       "objective_in_training_model": info["objective"]})
    return fitted, status


def eval_under_profile(scene: np.ndarray, fitted: dict, profile) -> dict:
    n = scene.shape[0]
    src = np.broadcast_to(scene, (3, n, n))
    target = {}
    pred = {name: {} for name in CONTROLS}
    errors = {name: [] for name in CONTROLS}
    for sign in SIGNS:
        base, desired = optics_otfs(profile, sign, n)
        target[sign] = mix_channels(
            optical_forward(src, desired), profile.channel_leakage
        )
        for name in CONTROLS:
            displayed = fitted[name][sign]
            light = code_to_light(displayed, profile.gamma_actual)
            y = mix_channels(
                optical_forward(light, base), profile.channel_leakage
            )
            pred[name][sign] = y
            errors[name].append(relative_l2(y, target[sign]))
    scores = {}
    for name in CONTROLS:
        result = signed_alignment(pred[name], target)
        scores[name] = {
            **result,
            "mean_assigned_l2": float(np.mean(errors[name])),
        }
    return scores


def execute(*, size: int = 64, maxiter: int = 90,
            scenes: tuple[str, ...] = FROZEN_SCENES,
            profiles=None) -> tuple[list[dict], dict]:
    if profiles is None:
        profiles = validation_profiles()
    if not scenes or not profiles:
        raise ValueError("nonempty scenes and profiles required")
    rows = []
    optimizer_status = []
    for scene_name in scenes:
        scene = make_scene(scene_name, size)
        fitted, status = fit_candidates(scene, maxiter=maxiter)
        optimizer_status.extend({"scene": scene_name, **s} for s in status)
        spread = {
            name: float(np.mean([artifact_proxy(fitted[name][v]) for v in SIGNS]))
            for name in MODELS
        }
        for profile in profiles:
            scores = eval_under_profile(scene, fitted, profile)
            row = {
                "scene": scene_name,
                "profile": profile.name,
                "target_separation": scores["mapped_rgb"]["target_separation"],
                "mapped_alignment": scores["mapped_rgb"]["alignment"],
                "permuted_fit_alignment": scores["permuted_fit_rgb"]["alignment"],
                "achromatic_fit_alignment": scores["achromatic_fit_rgb"]["alignment"],
                "gray_alignment": scores["optimized_gray"]["alignment"],
                "unmodified_alignment": scores["unmodified"]["alignment"],
                "mapped_l2": scores["mapped_rgb"]["mean_assigned_l2"],
                "permuted_fit_l2": scores["permuted_fit_rgb"]["mean_assigned_l2"],
                "achromatic_fit_l2": scores["achromatic_fit_rgb"]["mean_assigned_l2"],
                "gray_l2": scores["optimized_gray"]["mean_assigned_l2"],
                "mapped_chroma": spread["mapped_rgb"],
                "permuted_fit_chroma": spread["permuted_fit_rgb"],
                "achromatic_fit_chroma": spread["achromatic_fit_rgb"],
                "mapped_beats_permuted_alignment": (
                    scores["mapped_rgb"]["alignment"] > scores["permuted_fit_rgb"]["alignment"]
                    if scores["mapped_rgb"]["alignment"] is not None
                    and scores["permuted_fit_rgb"]["alignment"] is not None else None),
                "mapped_beats_achromatic_alignment": (
                    scores["mapped_rgb"]["alignment"] > scores["achromatic_fit_rgb"]["alignment"]
                    if scores["mapped_rgb"]["alignment"] is not None
                    and scores["achromatic_fit_rgb"]["alignment"] is not None else None),
                "scope": "SYNTHETIC_MODEL_MISMATCH_NO_EYE_DATA",
            }
            rows.append(row)
    defined = [r for r in rows if r["mapped_alignment"] is not None
               and r["permuted_fit_alignment"] is not None
               and r["achromatic_fit_alignment"] is not None]
    summary = {
        "study": STUDY,
        "n_scenes": len(scenes), "n_profiles": len(profiles), "rows": len(rows),
        "paired_directional_rows": len(defined),
        "all_optimizers_converged": all(s["success"] for s in optimizer_status),
        "optimization_status": optimizer_status,
        "hypotheses": {
            "mapped_rgb": "3HW RGB optimized for correct R2 channel order",
            "permuted_fit_rgb": "independently optimized 3HW RGB with R/B-swapped training PSF",
            "achromatic_fit_rgb": "independently optimized 3HW RGB under a channel-averaged training PSF",
            "optimized_gray": "separately optimized single HW field; lower capacity",
            "unmodified": "unchanged gray source",
        },
        "invariants": {
            "same_target_all_arms": True, "same_source_all_arms": True,
            "same_RGB_free_variable_count": True,
            "same_RGB_regularizers": [LAMBDA_DEVIATION, LAMBDA_CHROMA],
            "same_RGB_bounds": [0., 1.], "same_RGB_optimizer": "L-BFGS-B",
            "nulls_independently_refit": True,
        },
        "mapped_beats_permuted_alignment": sum(r["mapped_beats_permuted_alignment"] is True for r in defined),
        "mapped_beats_achromatic_alignment": sum(r["mapped_beats_achromatic_alignment"] is True for r in defined),
        "mapped_positive_alignment": sum(r["mapped_alignment"] > 0 for r in defined),
        "median_mapped_alignment": median(r["mapped_alignment"] for r in defined) if defined else None,
        "median_permuted_fit_alignment": median(r["permuted_fit_alignment"] for r in defined) if defined else None,
        "median_achromatic_fit_alignment": median(r["achromatic_fit_alignment"] for r in defined) if defined else None,
        "result_scope": "SIMULATOR_ONLY_NO_EYE_OR_SCREEN_MEASUREMENT",
        "limitations": [
            "Null models intentionally differ in forward operator, so matching parameter count does not isolate every confound",
            "All arms use targets generated by nominal R2 optics; chosen target favors a correctly specified training model",
            "R2 and R3 share scalar Fourier physics and an LCA relation",
            "Achromatic PSF is an average of RGB frequency responses, not actual physical color-independent eye optics",
            "Different RGB candidates may have different total chroma/luminance artifacts despite the same penalties",
            "No actual display spectra, monitor calibration, retinal optics, accommodation or eye-strain outcomes",
            "Only two synthetic scenes individually refitted; no universal filter",
        ],
    }
    return rows, summary


def write_outputs(directory: Path, rows: list[dict], summary: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "equal_capacity.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (directory / "summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    scripts = {
        "r2_inverse": BASE / "r2_display_inverse" / "inverse.py",
        "r3_eval": BASE / "r3_model_mismatch" / "evaluate.py",
        "r3_alt": BASE / "r3_model_mismatch" / "alt_optics.py",
        "r5_eval": Path(__file__).resolve(),
        "r5_metric": Path(__file__).with_name("directional_metric.py"),
    }
    (directory / "manifest.json").write_text(json.dumps({
        "study": STUDY,
        "sha256": {k: sha256(path.read_bytes()).hexdigest()
                   for k, path in scripts.items()},
        "files": ["equal_capacity.csv", "summary.json", "manifest.json"],
        "human_data": False, "optical_instrument_data": False,
    }, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--size", type=int, default=64)
    parser.add_argument("--maxiter", type=int, default=90)
    args = parser.parse_args()
    rows, summary = execute(size=args.size, maxiter=args.maxiter)
    write_outputs(args.out, rows, summary)
    print(json.dumps({
        "study": STUDY, "rows": summary["rows"],
        "mapped_beats_permuted_alignment": summary["mapped_beats_permuted_alignment"],
        "mapped_beats_achromatic_alignment": summary["mapped_beats_achromatic_alignment"],
        "result_scope": summary["result_scope"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
