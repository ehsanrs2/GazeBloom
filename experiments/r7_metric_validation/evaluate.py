#!/usr/bin/env python3
"""R7: predeclared conditioning for R4's template score + target-free focus scan.

All optical profiles, targets and displayed images are synthetic. Neither
metric represents measured ocular accommodation or a therapeutic effect.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from math import sqrt
from pathlib import Path
from statistics import median
import sys

import numpy as np

EXPERIMENTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXPERIMENTS.parent))
sys.path.insert(0, str(EXPERIMENTS / "r3_model_mismatch"))

from experiments.r3_model_mismatch.evaluate import FROZEN_SCENES, make_scene
from experiments.r3_model_mismatch.alt_optics import (
    code_to_light, mix_channels, optical_forward, optics_otfs,
    validation_profiles,
)
from experiments.r5_equal_capacity_controls.evaluate import MODELS
from experiments.r6_identifiability.evaluate import (
    SIGNS, TARGET_GENERATOR, cross_generated_fit, match_scene_pair,
)
from experiments.r4_directional_controls.evaluate import signed_alignment

STUDY = "R7_CONDITIONED_TEMPLATE_AND_FOCUS_SCAN_V1"
FOCUS_GRID_D = (-0.75, -0.50, -0.25, 0.0, 0.25, 0.50, 0.75)
SIGNIFICANCE_HEURISTIC_SIGMA = 10.0
TARGET_RELATIVE_FLOOR = 0.02
# Explicitly a simple input-domain 8-bit numerical resolution heuristic,
# NOT a calibrated retinal noise measurement or validated statistical test.
PAIR_QUANTIZATION_RMS_PROXY = sqrt(2.) / (255. * sqrt(12.))


def target_pair(scene: np.ndarray, profile, *,
                same_channel_psf: bool = False) -> dict[float, np.ndarray]:
    """Construct R3 toy targets only for the template diagnostic."""
    n = scene.shape[0]
    src = np.broadcast_to(scene, (3, n, n))
    out = {}
    for sign in SIGNS:
        _, target_otfs = optics_otfs(profile, sign, n)
        if same_channel_psf:
            target_otfs = np.broadcast_to(target_otfs[1:2], target_otfs.shape)
        out[sign] = mix_channels(
            optical_forward(src, target_otfs), profile.channel_leakage)
    return out


def conditioning_gate(target: dict[float, np.ndarray]) -> dict:
    """Predeclared dimensional threshold for model-template separation.

    A prior numeric resolution heuristic is deliberately conservative.
    It does NOT quantify actual optical uncertainty or imply 10-sigma
    physiological confidence.
    """
    if set(target) != set(SIGNS):
        raise ValueError("targets must have both signed labels")
    a, b = target[SIGNS[0]], target[SIGNS[1]]
    if a.shape != b.shape or a.ndim != 3 or a.shape[0] != 3:
        raise ValueError("equal-shape RGB target images required")
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("nonfinite target image")
    separation = float(np.sqrt(np.mean((a-b)**2)))
    typical = float(np.sqrt(.5 * (np.mean(a*a) + np.mean(b*b))))
    quantization_floor = SIGNIFICANCE_HEURISTIC_SIGMA * PAIR_QUANTIZATION_RMS_PROXY
    relative_floor = TARGET_RELATIVE_FLOOR * typical
    threshold = max(quantization_floor, relative_floor)
    return {
        "target_sep_rms": separation,
        "target_rms": typical,
        "resolution_floor": quantization_floor,
        "relative_floor": relative_floor,
        "required_sep_rms": threshold,
        "well_conditioned": bool(separation > threshold),
        "quality_flag": "USABLE_IN_SIMULATION_ONLY" if separation > threshold
                        else "ABSTAIN_NEAR_DEGENERATE_TARGETS",
        "ratio_sep_to_floor": float(separation / threshold),
    }


def conditioned_alignment(predicted: dict[float, np.ndarray],
                          target: dict[float, np.ndarray]) -> dict:
    """Preserve historical score but never interpret poorly separated targets."""
    gate = conditioning_gate(target)
    raw = signed_alignment(predicted, target)
    return {
        **gate,
        "historical_raw_A": raw["alignment"],
        "conditioned_A": raw["alignment"] if gate["well_conditioned"] else None,
        "correct_template_count": raw["correct_template_count"]
        if gate["well_conditioned"] else None,
    }


def retinal_focus_curve(rgb_linear: np.ndarray, profile, *,
                        same_channel_psf: bool = False,
                        quantized: bool = False) -> list[float]:
    """Target-independent edge-energy proxy across hypothetical eye defocus.

    No desired/target retinal template is used. This is a simulated optical
    sharpness criterion; it is NOT an eye-controller or human focus preference.
    """
    if rgb_linear.ndim != 3 or rgb_linear.shape[0] != 3:
        raise ValueError("RGB field required")
    n = rgb_linear.shape[1]
    if rgb_linear.shape[2] != n:
        raise ValueError("square crop required")
    if not np.isfinite(rgb_linear).all() or rgb_linear.min() < -1e-10 or rgb_linear.max() > 1+1e-10:
        raise ValueError("RGB field must be finite and bounded")
    display = code_to_light(rgb_linear, profile.gamma_actual) if quantized else rgb_linear
    # Same Rec.709-like linear RGB coefficients as R6, but not a measured cone
    # sensitivity or luminance response of any real human.
    weights = np.array((.2126, .7152, .0722))
    curve = []
    for focus in FOCUS_GRID_D:
        _, otf = optics_otfs(profile, focus, n)
        if same_channel_psf:
            otf = np.broadcast_to(otf[1:2], otf.shape)
        retina = mix_channels(
            optical_forward(display, otf), profile.channel_leakage)
        luminance = np.einsum("c,chw->hw", weights, retina)
        # Periodic central-gradient energy; compatible with the circular
        # convolution model. Does not inspect the constructed target.
        gx = .5 * (np.roll(luminance, -1, axis=1)
                    - np.roll(luminance, 1, axis=1))
        gy = .5 * (np.roll(luminance, -1, axis=0)
                    - np.roll(luminance, 1, axis=0))
        curve.append(float(np.mean(gx*gx + gy*gy)))
    return curve


def preference_summary(curve_minus: list[float],
                       curve_plus: list[float]) -> dict:
    """Discrete focus-grid peaks; no interpolation and no causal interpretation."""
    minus, plus = np.asarray(curve_minus), np.asarray(curve_plus)
    if minus.shape != (len(FOCUS_GRID_D),) or plus.shape != minus.shape:
        raise ValueError("must supply two focus curves on frozen grid")
    if not np.isfinite(minus).all() or not np.isfinite(plus).all():
        raise ValueError("nonfinite sharpness")
    idx_minus, idx_plus = int(np.argmax(minus)), int(np.argmax(plus))
    grid = np.array(FOCUS_GRID_D)
    mean_level = float(max(.5 * (minus.mean() + plus.mean()), 1e-14))
    return {
        "minus_peak_D": float(grid[idx_minus]),
        "plus_peak_D": float(grid[idx_plus]),
        "delta_peak_D": float(grid[idx_plus] - grid[idx_minus]),
        "any_boundary_peak": idx_minus in (0, len(grid)-1)
                             or idx_plus in (0, len(grid)-1),
        "relative_curve_difference": float(np.sqrt(np.mean((minus-plus)**2))
                                           / mean_level),
        "curve_score_span_minus": float((minus.max()-minus.min()) / mean_level),
        "curve_score_span_plus": float((plus.max()-plus.min()) / mean_level),
        "quantity": "TARGET_FREE_SYNTHETIC_GRADIENT_ENERGY_NOT_ACCOMMODATION",
    }


def execute(*, size: int = 64, maxiter: int = 90,
            scenes=FROZEN_SCENES, profiles=None, generator=None) -> tuple[list[dict], dict]:
    if generator is None:
        generator = next(p for p in validation_profiles()
                         if p.name == TARGET_GENERATOR)
    if profiles is None:
        profiles = tuple(p for p in validation_profiles()
                         if p.name != generator.name)
    if not profiles or not scenes or generator.name in {p.name for p in profiles}:
        raise ValueError("nonempty held-out models and scenes required")
    if size < 50 or size % 2 or maxiter < 1:
        raise ValueError("invalid image grid or iteration budget")
    rows, fit_status, matched_stats = [], [], []
    for scene_name in scenes:
        scene = make_scene(scene_name, size)
        raw, statuses = cross_generated_fit(
            scene, generator=generator, maxiter=maxiter)
        matched, stats = match_scene_pair(scene, raw)
        fit_status.extend({"scene":scene_name, **x} for x in statuses)
        matched_stats.append({"scene":scene_name, **stats})
        for profile in profiles:
            targets = target_pair(scene, profile)
            null_targets = target_pair(scene, profile,
                                       same_channel_psf=True)
            gate = conditioning_gate(targets)
            null_gate = conditioning_gate(null_targets)
            row = {
                "scene": scene_name,
                "profile": profile.name,
                "target_generator": generator.name,
                "target_sep_rms": gate["target_sep_rms"],
                "target_gate": gate["quality_flag"],
                "target_sep_over_floor": gate["ratio_sep_to_floor"],
                "common_psf_target_sep_rms": null_gate["target_sep_rms"],
                "common_psf_target_gate": null_gate["quality_flag"],
            }
            for model in MODELS:
                predictions = {}
                for sign in SIGNS:
                    base, _unused = optics_otfs(profile, sign, size)
                    light = code_to_light(matched[model][sign], profile.gamma_actual)
                    pred = mix_channels(
                        optical_forward(light, base), profile.channel_leakage)
                    predictions[sign] = pred
                alignment = conditioned_alignment(predictions, targets)
                row[f"{model}_historical_A"] = alignment["historical_raw_A"]
                row[f"{model}_conditioned_A"] = alignment["conditioned_A"]
                minus_curve = retinal_focus_curve(matched[model][SIGNS[0]], profile)
                plus_curve = retinal_focus_curve(matched[model][SIGNS[1]], profile)
                focus = preference_summary(minus_curve, plus_curve)
                row[f"{model}_focus_delta_peak_D"] = focus["delta_peak_D"]
                row[f"{model}_focus_curve_relative_difference"] = focus[
                    "relative_curve_difference"]
                row[f"{model}_focus_boundary_peak"] = focus["any_boundary_peak"]
                # Strong null: remove all interchannel PSF differences.
                # In ideal (nonquantized) linear light, the R6-assumed
                # weighted luminance is exactly scene for every candidate.
                null_minus = retinal_focus_curve(
                    matched[model][SIGNS[0]], profile, same_channel_psf=True)
                null_plus = retinal_focus_curve(
                    matched[model][SIGNS[1]], profile, same_channel_psf=True)
                common = preference_summary(null_minus, null_plus)
                row[f"{model}_common_psf_focus_curve_difference"] = common[
                    "relative_curve_difference"]
            row["scope"] = "MODEL_ONLY_CONDITIONED_A_AND_TARGET_FREE_FOCUS_PROXY"
            rows.append(row)

    good = [r for r in rows if r["target_gate"]=="USABLE_IN_SIMULATION_ONLY"]
    nulled = [r for r in rows
              if r["common_psf_target_gate"]=="ABSTAIN_NEAR_DEGENERATE_TARGETS"]
    summary = {
        "study": STUDY,
        "rows": len(rows), "scenes": list(scenes),
        "generator_name": generator.name,
        "evaluation_profiles": [p.name for p in profiles],
        "fit_status": fit_status,
        "all_optimizer_success": all(x["success"] for x in fit_status),
        "matching": matched_stats,
        "target_gate": {
            "quantization_pair_sigma_proxy": PAIR_QUANTIZATION_RMS_PROXY,
            "quantization_multiplier": SIGNIFICANCE_HEURISTIC_SIGMA,
            "relative_target_rms_floor": TARGET_RELATIVE_FLOOR,
            "min_separation_definition": "max(10*sqrt(2)/(255*sqrt(12)),0.02*RMS(target_pair))",
            "heuristic_not_calibrated": True,
            "usable_regular_rows": len(good),
            "abstained_common_psf_control_rows": len(nulled),
        },
        "median_conditioned_mapped_A": (
            median(r["mapped_rgb_conditioned_A"] for r in good) if good else None),
        "median_conditioned_achromatic_A": (
            median(r["achromatic_fit_rgb_conditioned_A"] for r in good) if good else None),
        "mapped_better_than_achromatic_in_usable_rows": sum(
            r["mapped_rgb_conditioned_A"] > r["achromatic_fit_rgb_conditioned_A"]
            for r in good),
        "focus_grid_D": list(FOCUS_GRID_D),
        "focus_proxy": "periodic centered-gradient energy of assumed luminance; "
                       "argmax sampled synthetic defocus, NOT a measured eye response",
        "common_psf_focus_control_max_curve_difference": max(
            r[f"{m}_common_psf_focus_curve_difference"]
            for r in rows for m in MODELS),
        "reported_limitations": [
            "8-bit uniform quantization and 10-sigma are heuristic, not measured optical uncertainty",
            "Target metric still uses synthetic target labels; only sharpness scan is template-free",
            "Sharpness maximization is a computational autofocus assumption and not human accommodation",
            "All 3 channel OTFs equal to green is an all-channel PSF ablation, not LCA-only knockout",
            "Focus peak estimates are discretized and boundary-censored; no smooth response or closed loop",
            "Cross-target producer and evaluator share scalar optics, chromatic relation, synthetic displays",
            "R6 luminance/chroma matching not equal to spectral or perceptual color matching",
            "No human participant, eye tracking, autorefractor or eye-strain outcome was involved",
        ],
        "human_accommodation": "NOT_MEASURED",
        "clinical_claim": "NONE",
    }
    return rows, summary


def write_results(out: Path, rows: list[dict], summary: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out/"r7_metrics.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out/"summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2)+"\n",encoding="utf-8")
    files = {n: EXPERIMENTS/n for n in (
        "r3_model_mismatch/alt_optics.py",
        "r4_directional_controls/evaluate.py",
        "r5_equal_capacity_controls/evaluate.py",
        "r6_identifiability/evaluate.py",
        "r7_metric_validation/evaluate.py",
    )}
    (out/"manifest.json").write_text(
        json.dumps({
            "study": STUDY, "code_sha256": {
                k: sha256(p.read_bytes()).hexdigest() for k,p in files.items()},
            "files":["r7_metrics.csv","summary.json","manifest.json"],
            "claims":"IN_SILICO_ONLY_NO_PHYSIOLOGY_OR_HEALTHCARE",
        },sort_keys=True,indent=2)+"\n",encoding="utf-8")


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--size",type=int,default=64)
    p.add_argument("--maxiter",type=int,default=90)
    args=p.parse_args()
    rows,summary=execute(size=args.size,maxiter=args.maxiter)
    write_results(args.out,rows,summary)
    print(json.dumps({
        "study":STUDY,"rows":summary["rows"],
        "usable_regular":summary["target_gate"]["usable_regular_rows"],
        "abstained_common_psf":summary["target_gate"]["abstained_common_psf_control_rows"],
        "focus_null_max":summary["common_psf_focus_control_max_curve_difference"],
        "human_accommodation":"NOT_MEASURED",
    },sort_keys=True))


if __name__=="__main__":
    main()
