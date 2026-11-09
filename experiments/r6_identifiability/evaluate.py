#!/usr/bin/env python3
"""R6: cross-generator targets, color/luminance matching and achromatic ablation.

The stimuli, optical targets and viewing profiles are ALL synthetic. This is
a falsification-oriented identification audit, NOT an accommodation model or
clinical evidence. No display spectrum, eye or human response is measured.
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

EXPERIMENTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXPERIMENTS.parent))
sys.path.insert(0, str(EXPERIMENTS / "r2_display_inverse"))
sys.path.insert(0, str(EXPERIMENTS / "r3_model_mismatch"))
sys.path.insert(0, str(EXPERIMENTS / "r5_equal_capacity_controls"))
from inverse import optical_otfs, optimize_display, forward  # noqa: E402
from alt_optics import (code_to_light, mix_channels, optical_forward,
                        optics_otfs, relative_l2, validation_profiles)  # noqa: E402
from experiments.r3_model_mismatch.evaluate import FROZEN_SCENES, make_scene  # noqa: E402
from experiments.r5_equal_capacity_controls.evaluate import (  # noqa: E402
    MODELS, LAMBDA_DEVIATION, LAMBDA_CHROMA, surrogate_operator
)
from experiments.r4_directional_controls.evaluate import signed_alignment  # noqa: E402

STUDY = "R6_CROSS_GENERATOR_LUMINANCE_CHROMA_MATCH_V1"
SIGNS = (-.45, .45)
REC709_ASSUMED_LINEAR_WEIGHTS = np.array((.2126, .7152, .0722))
CHROMA_CAP = .020  # chosen prior to R6 results; average absolute deviation
TARGET_GENERATOR = "spectral_aberrated"
NULL_NAME = "GREEN_PSF_ALL_CHANNELS_NOT_PURE_LCA_REMOVAL"


def linear_luminance(rgb: np.ndarray) -> np.ndarray:
    if rgb.ndim != 3 or rgb.shape[0] != 3 or not np.isfinite(rgb).all():
        raise ValueError("finite 3-channel RGB required")
    return np.einsum("c,chw->hw", REC709_ASSUMED_LINEAR_WEIGHTS, rgb)


def chromatic_deviation(rgb: np.ndarray) -> np.ndarray:
    return rgb - linear_luminance(rgb)[None, ...]


def matching_limit(rgb: np.ndarray, gray_reference: np.ndarray) -> tuple[float, float]:
    """Largest nonamplifying chroma scale preserving exact assumed luminance.

    No clipping is performed. A shared scalar is selected without looking at
    any retinal error or target metric.
    """
    if gray_reference.ndim != 2 or rgb.shape != (3,) + gray_reference.shape:
        raise ValueError("incompatible image dimensions")
    if not np.isfinite(gray_reference).all() or gray_reference.min() < 0 or gray_reference.max() > 1:
        raise ValueError("reference must be finite in [0,1]")
    if rgb.min() < -1e-10 or rgb.max() > 1 + 1e-10:
        raise ValueError("candidate outside RGB gamut")
    c = chromatic_deviation(rgb)
    r = np.broadcast_to(gray_reference, c.shape)
    positive = c > 1e-12
    negative = c < -1e-12
    limit = 1.
    if positive.any():
        limit = min(limit, float(np.min((1. - r[positive]) / c[positive])))
    if negative.any():
        limit = min(limit, float(np.min(r[negative] / (-c[negative]))))
    energy = float(np.mean(np.abs(c)))
    if not np.isfinite(limit) or limit < -1e-10:
        raise ValueError("no nonnegative feasible scaling factor")
    return max(limit, 0.), energy


def match_scene_pair(scene: np.ndarray, fitted: dict) -> tuple[dict, dict]:
    """Luminance equalized to input scene and chroma to a common budget.

    The budget is the minimum feasible among all arms and both signed images,
    capped at CHROMA_CAP. This is within-scene budget selection from stimulus
    geometry; it does NOT use the scoring model or reference targets.
    """
    candidates = [(name, sign, fitted[name][sign])
                  for name in MODELS for sign in SIGNS]
    if len(candidates) != 6:
        raise ValueError("three RGB arms and both signs are mandatory")
    limits = {(name, sign): matching_limit(rgb, scene)
              for name, sign, rgb in candidates}
    available = [limit * energy for limit, energy in limits.values()]
    budget = min(CHROMA_CAP, *available)
    if not np.isfinite(budget) or budget <= 1e-10:
        raise ValueError("matching unavailable: one arm has no feasible chroma budget")

    result = {name: {} for name in MODELS}
    stats = {"common_chroma_abs": budget,
             "max_assumed_linear_luminance_mismatch": 0.,
             "max_chroma_abs_mismatch": 0.,
             "selection": "min feasible chroma of all 6 candidate images, cap 0.020",
             "reference_luminance": "achromatic input scene, not measured cd/m^2"}
    for name, sign, rgb in candidates:
        _, energy = limits[name, sign]
        alpha = budget / energy
        # Only scale existing chroma structure, not a new optimization.
        new = scene[None, ...] + alpha * chromatic_deviation(rgb)
        error = float(np.max(np.abs(linear_luminance(new) - scene)))
        chroma_error = abs(float(np.mean(np.abs(chromatic_deviation(new)))) - budget)
        if new.min() < -1e-9 or new.max() > 1 + 1e-9:
            raise AssertionError("unexpected gamut violation")
        if error > 1e-10 or chroma_error > 1e-10 or alpha > 1.00000001:
            raise AssertionError("failed exact proxy-budget match")
        result[name][sign] = new
        stats["max_assumed_linear_luminance_mismatch"] = max(
            stats["max_assumed_linear_luminance_mismatch"], error)
        stats["max_chroma_abs_mismatch"] = max(
            stats["max_chroma_abs_mismatch"], chroma_error)
    return result, stats


def cross_generated_fit(scene: np.ndarray, *, generator, maxiter: int = 90) -> tuple[dict, list]:
    """Targets come from R3 alternative engine; training ops still R2.

    The target generator is fixed and excluded from held-out scoring.
    """
    n = scene.shape[0]
    if scene.shape != (n, n) or n < 50 or n % 2 or maxiter <= 0:
        raise ValueError("even square >=50 and positive maxiter required")
    initial = np.broadcast_to(scene, (3, n, n)).copy()
    results = {name: {} for name in MODELS}
    status = []
    for sign in SIGNS:
        # Critically this is NOT R2's nominal target operator:
        _, alternative_target_otf = optics_otfs(generator, sign, n)
        target = optical_forward(initial, alternative_target_otf)
        base, _unused_nominal_target = optical_otfs(4., sign, size=n)
        for name in MODELS:
            rgb, info = optimize_display(
                surrogate_operator(base, name), target, scene,
                shared=False, lambda_deviation=LAMBDA_DEVIATION,
                lambda_chroma=LAMBDA_CHROMA, maxiter=maxiter,
            )
            if rgb.shape != initial.shape or rgb.min() < -1e-10 or rgb.max() > 1 + 1e-10:
                raise AssertionError("optimization violates RGB field constraints")
            results[name][sign] = rgb
            status.append({
                "sign_D": sign, "arm": name, "free_parameters": 3*n*n,
                "success": info["optimizer_success"],
                "iterations": info["iterations"],
                "nominal_R2_target_used": False,
            })
    return results, status


def score_pair(scene: np.ndarray, candidates: dict, profile,
               *, no_channel_difference: bool = False) -> dict:
    """Score R4 signed synthetic template alignment with R3 holdout model."""
    n = scene.shape[0]
    initial = np.broadcast_to(scene, (3, n, n))
    target, predictions = {}, {name: {} for name in MODELS}
    l2 = {name: [] for name in MODELS}
    for sign in SIGNS:
        base, desired = optics_otfs(profile, sign, n)
        if no_channel_difference:
            # Strong achromatic-optics ablation. Removes *all* channel
            # dependence, not LCA alone: state this explicitly.
            base = np.broadcast_to(base[1:2], base.shape)
            desired = np.broadcast_to(desired[1:2], desired.shape)
        target[sign] = mix_channels(
            optical_forward(initial, desired), profile.channel_leakage)
        for name in MODELS:
            light = code_to_light(candidates[name][sign], profile.gamma_actual)
            pred = mix_channels(
                optical_forward(light, base), profile.channel_leakage)
            predictions[name][sign] = pred
            l2[name].append(relative_l2(pred, target[sign]))
    return {
        name: {**signed_alignment(predictions[name], target),
               "mean_l2": float(np.mean(l2[name]))}
        for name in MODELS
    }


def run(*, scenes=FROZEN_SCENES, size: int = 64, maxiter: int = 90,
        profiles=None, generator=None) -> tuple[list[dict], dict]:
    if profiles is None:
        profiles = tuple(p for p in validation_profiles()
                         if p.name != TARGET_GENERATOR)
    if generator is None:
        generator = next(p for p in validation_profiles()
                         if p.name == TARGET_GENERATOR)
    if generator.name in {p.name for p in profiles}:
        raise ValueError("target generator must not be included as a holdout evaluator")
    if not scenes or not profiles or size < 50 or size % 2 or maxiter < 1:
        raise ValueError("invalid frozen study configuration")
    rows, fit_status, scene_stats = [], [], []
    for scene_name in scenes:
        scene = make_scene(scene_name, size)
        raw, statuses = cross_generated_fit(scene, generator=generator, maxiter=maxiter)
        fit_status.extend([{"scene": scene_name, **s} for s in statuses])
        matched, stats = match_scene_pair(scene, raw)
        scene_stats.append({"scene": scene_name, **stats})
        for profile in profiles:
            raw_score = score_pair(scene, raw, profile)
            matched_score = score_pair(scene, matched, profile)
            null_score = score_pair(scene, matched, profile,
                                    no_channel_difference=True)
            row = {
                "scene": scene_name,
                "profile": profile.name,
                "target_generator": generator.name,
                "raw_mapped_A": raw_score["mapped_rgb"]["alignment"],
                "raw_permuted_A": raw_score["permuted_fit_rgb"]["alignment"],
                "raw_achromatic_A": raw_score["achromatic_fit_rgb"]["alignment"],
                "matched_mapped_A": matched_score["mapped_rgb"]["alignment"],
                "matched_permuted_A": matched_score["permuted_fit_rgb"]["alignment"],
                "matched_achromatic_A": matched_score["achromatic_fit_rgb"]["alignment"],
                "matched_mapped_l2": matched_score["mapped_rgb"]["mean_l2"],
                "matched_permuted_l2": matched_score["permuted_fit_rgb"]["mean_l2"],
                "matched_achromatic_l2": matched_score["achromatic_fit_rgb"]["mean_l2"],
                "achromatic_psf_null_mapped_A": null_score["mapped_rgb"]["alignment"],
                "achromatic_psf_null_target_separation": null_score["mapped_rgb"]["target_separation"],
                "common_chroma_abs": stats["common_chroma_abs"],
                "max_luminance_mismatch": stats["max_assumed_linear_luminance_mismatch"],
                "mapped_gt_permuted_matched": (
                    matched_score["mapped_rgb"]["alignment"] > matched_score["permuted_fit_rgb"]["alignment"]
                    if matched_score["mapped_rgb"]["alignment"] is not None
                    and matched_score["permuted_fit_rgb"]["alignment"] is not None else None),
                "mapped_gt_achromatic_matched": (
                    matched_score["mapped_rgb"]["alignment"] > matched_score["achromatic_fit_rgb"]["alignment"]
                    if matched_score["mapped_rgb"]["alignment"] is not None
                    and matched_score["achromatic_fit_rgb"]["alignment"] is not None else None),
                "scope": "SYNTHETIC_CROSS_TARGET_AND_PROXY_MATCHING_ONLY",
            }
            rows.append(row)
    defined = [x for x in rows if all(x[k] is not None for k in
               ("matched_mapped_A", "matched_permuted_A",
                "matched_achromatic_A"))]
    summary = {
        "study": STUDY,
        "rows": len(rows), "directional_defined_rows": len(defined),
        "scenes": list(scenes), "target_generator": generator.__dict__,
        "evaluation_profiles": [p.name for p in profiles],
        "fit_status": fit_status,
        "all_optimizer_success": all(x["success"] for x in fit_status),
        "scene_matching_stats": scene_stats,
        "mapped_gt_permuted_matched_count": sum(x["mapped_gt_permuted_matched"] is True for x in defined),
        "mapped_gt_achromatic_matched_count": sum(x["mapped_gt_achromatic_matched"] is True for x in defined),
        "median_matched_mapped_A": median(x["matched_mapped_A"] for x in defined) if defined else None,
        "median_matched_permuted_A": median(x["matched_permuted_A"] for x in defined) if defined else None,
        "median_matched_achromatic_A": median(x["matched_achromatic_A"] for x in defined) if defined else None,
        "achromatic_psf_null_defined_rows": sum(x["achromatic_psf_null_mapped_A"] is not None for x in rows),
        "null_interpretation": (
            "All 3 channel OTFs replaced by green: ablates ALL RGB optical "
            "differences, not LCA in isolation. Undefined target signs are "
            "recorded as null rather than zero."
        ),
        "luminance_interpretation": (
            "Rec.709 coefficients assumed for an imaginary linear-light "
            "display, not calibrated display luminance or SPD."
        ),
        "chroma_interpretation": (
            "Shared mean absolute deviation from weighted luminance, not "
            "perceptually equal or spectrally equal chromatic energy."
        ),
        "claims": {"human_accommodation": "NOT_MEASURED",
                   "optical_physical_validation": "NOT_MEASURED",
                   "eye_strain_or_safety": "NOT_MEASURED"},
        "status": "MODEL_IDENTIFIABILITY_DIAGNOSTIC_ONLY",
    }
    return rows, summary


def write_results(out: Path, rows: list[dict], summary: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "identifiability.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    scripts = {name: EXPERIMENTS / name for name in (
        "r2_display_inverse/inverse.py",
        "r3_model_mismatch/alt_optics.py",
        "r3_model_mismatch/evaluate.py",
        "r4_directional_controls/evaluate.py",
        "r5_equal_capacity_controls/evaluate.py",
        "r6_identifiability/evaluate.py",
    )}
    (out / "manifest.json").write_text(json.dumps({
        "study": STUDY,
        "source_sha256": {n: sha256(p.read_bytes()).hexdigest()
                          for n, p in scripts.items()},
        "products": ["identifiability.csv", "summary.json", "manifest.json"],
        "data_kind": "synthetic-only no physical ocular measurement",
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--size", type=int, default=64)
    p.add_argument("--maxiter", type=int, default=90)
    args = p.parse_args()
    rows, summary = run(size=args.size, maxiter=args.maxiter)
    write_results(args.out, rows, summary)
    print(json.dumps({
        "study": STUDY, "rows": summary["rows"],
        "matched_mapped_beats_permuted": summary["mapped_gt_permuted_matched_count"],
        "matched_mapped_beats_achromatic": summary["mapped_gt_achromatic_matched_count"],
        "achromatic_null_defined_rows": summary["achromatic_psf_null_defined_rows"],
        "scientific_status": summary["status"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
