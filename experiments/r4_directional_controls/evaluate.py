#!/usr/bin/env python3
"""GazeBloom R4: signed synthetic template alignment and RGB-order controls.

This is deliberately NOT an accommodation-response predictor. Scores describe
geometry of simulated retinal images only. Fitting uses R2 optical model;
scoring uses R3's alternative toy scalar optics. No physiology is measured.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "r2_display_inverse"))
sys.path.insert(0, str(ROOT / "r3_model_mismatch"))
from inverse import forward, optical_otfs, optimize_display  # noqa: E402
from evaluate import FROZEN_SCENES, make_scene  # noqa: E402
from alt_optics import (code_to_light, mix_channels, optical_forward, optics_otfs,
                        validation_profiles, relative_l2)  # noqa: E402

VERSION = "R4_SIGNED_RGB_MAPPING_STRESS_V1"
SIGNS = (-0.45, 0.45)
MAP_RB_SWAP = (2, 1, 0)
VARIANTS = ("unmodified", "gray", "rgb", "rgb_rb_swapped")


def swapped_channels(rgb: np.ndarray) -> np.ndarray:
    """Exact R/B channel mapping null: preserves RGB value multiset and chroma."""
    if rgb.ndim != 3 or rgb.shape[0] != 3:
        raise ValueError("expected linear RGB image with 3 channels")
    return rgb[np.array(MAP_RB_SWAP)].copy()


def scene_artifacts(source: np.ndarray, rgb: np.ndarray) -> dict:
    """Non-perceptual proxies only: normalized channel spread and edge chroma."""
    if rgb.shape != (3,) + source.shape:
        raise ValueError("invalid RGB shape")
    chroma = np.abs(rgb - rgb.mean(axis=0, keepdims=True)).mean(axis=0)
    edge = np.abs(source - np.roll(source, 1, axis=0)) + np.abs(
        source - np.roll(source, 1, axis=1))
    mask = edge >= np.quantile(edge, .75)
    return {
        "mean_abs_chroma": float(np.mean(chroma)),
        "edge_chroma_mean": float(chroma[mask].mean()),
        "nonedge_chroma_mean": float(chroma[~mask].mean()) if (~mask).any() else None,
        "saturated_channel_fraction": float(np.mean((rgb <= 1e-9) | (rgb >= 1 - 1e-9))),
        "scope": "NUMERICAL_ARTIFACT_PROXY_NOT_PERCEPTUAL_ASSESSMENT",
    }


def signed_alignment(pred: dict[float, np.ndarray],
                     target: dict[float, np.ndarray]) -> dict:
    """Difference-in-differences for signed retinal-template distances.

    For target T+,T- and display predictions P+,P-:
      alignment = (||P+-T-||² + ||P--T+||²
                   -||P+-T+||² -||P--T-||²)/(2||T+-T-||²).
    Identical images => 0, perfect match => 1; unbounded, not probability.
    This is a diagnostic of *model template ordering*, NOT response direction.
    """
    minus, plus = SIGNS
    if set(pred) != set(SIGNS) or set(target) != set(SIGNS):
        raise ValueError("both signed candidate and target arrays are required")
    if pred[plus].shape != target[plus].shape or any(
        a.shape != target[plus].shape for a in
        (pred[minus], target[minus])
    ):
        raise ValueError("prediction/target shape mismatch")
    if not all(np.isfinite(x).all() for x in (*pred.values(), *target.values())):
        raise ValueError("nonfinite images")
    def squared(a, b):
        return float(np.sum((a-b)**2))
    target_distance = squared(target[plus], target[minus])
    if target_distance <= 1e-15:
        return {"alignment": None, "target_separation": 0.0,
                "correct_template_count": None}
    e_pp = squared(pred[plus], target[plus])
    e_mm = squared(pred[minus], target[minus])
    e_pm = squared(pred[plus], target[minus])
    e_mp = squared(pred[minus], target[plus])
    return {
        "alignment": (e_pm + e_mp - e_pp - e_mm) / (2 * target_distance),
        "target_separation": float(np.sqrt(target_distance / target[plus].size)),
        "correct_template_count": int(e_pp < e_pm) + int(e_mm < e_mp),
    }


def fit_signed_pair(scene: np.ndarray, *, size: int, maxiter: int) -> tuple[dict, list]:
    if scene.shape != (size, size):
        raise ValueError("scene dimension mismatch")
    rgb_source = np.broadcast_to(scene, (3, size, size)).copy()
    pair = {v: {} for v in VARIANTS}
    statuses = []
    for sign in SIGNS:
        base_otf, target_otf = optical_otfs(4., sign, size=size)
        target = forward(rgb_source, target_otf)
        gray, a = optimize_display(base_otf, target, scene, shared=True,
                                   maxiter=maxiter)
        rgb, b = optimize_display(base_otf, target, scene, shared=False,
                                  maxiter=maxiter)
        pair["unmodified"][sign] = rgb_source
        pair["gray"][sign] = gray
        pair["rgb"][sign] = rgb
        pair["rgb_rb_swapped"][sign] = swapped_channels(rgb)
        statuses.append({
            "sign_D": sign, "gray_success": a["optimizer_success"],
            "rgb_success": b["optimizer_success"],
            "gray_iterations": a["iterations"], "rgb_iterations": b["iterations"],
        })
    return pair, statuses


def score_profile(scene: np.ndarray, pair: dict, profile, *, size: int) -> dict:
    target = {}
    otfs = {}
    src = np.broadcast_to(scene, (3, size, size))
    for sign in SIGNS:
        base, desired = optics_otfs(profile, sign, size)
        target[sign] = mix_channels(
            optical_forward(src, desired), profile.channel_leakage)
        otfs[sign] = base
    result = {}
    for name in VARIANTS:
        predicted = {}
        assigned_relative_error = {}
        for sign in SIGNS:
            display = pair[name][sign]
            light = code_to_light(display, profile.gamma_actual)
            prediction = mix_channels(
                optical_forward(light, otfs[sign]), profile.channel_leakage)
            predicted[sign] = prediction
            assigned_relative_error[sign] = relative_l2(prediction, target[sign])
        ordering = signed_alignment(predicted, target)
        result[name] = {
            **ordering,
            "mean_assigned_relative_l2": float(
                np.mean(list(assigned_relative_error.values()))),
        }
    return result


def run(*, size: int = 64, maxiter: int = 90,
        scenes: tuple[str, ...] = FROZEN_SCENES,
        profiles=None) -> tuple[list[dict], dict]:
    if size < 50 or size % 2 or maxiter < 1:
        raise ValueError("requires even image size >=50, positive maxiter")
    if profiles is None:
        profiles = validation_profiles()
    if not scenes or not profiles:
        raise ValueError("at least one scene and evaluator profile required")
    rows = []
    optimizers = []
    for scene_name in scenes:
        scene = make_scene(scene_name, size)
        pair, statuses = fit_signed_pair(scene, size=size, maxiter=maxiter)
        optimizers += [{"scene": scene_name, **status} for status in statuses]
        proxies = {str(sign): scene_artifacts(scene, pair["rgb"][sign])
                   for sign in SIGNS}
        for profile in profiles:
            scored = score_profile(scene, pair, profile, size=size)
            values = {name: scored[name]["alignment"] for name in VARIANTS}
            rows.append({
                "scene": scene_name, "profile": profile.name,
                "target_separation": scored["rgb"]["target_separation"],
                "rgb_alignment": values["rgb"],
                "gray_alignment": values["gray"],
                "rb_swap_alignment": values["rgb_rb_swapped"],
                "unmodified_alignment": values["unmodified"],
                "rgb_correct_template_count": scored["rgb"]["correct_template_count"],
                "gray_correct_template_count": scored["gray"]["correct_template_count"],
                "swap_correct_template_count": scored["rgb_rb_swapped"]["correct_template_count"],
                "rgb_beats_rb_swap": None,
            })
            # Fill explicit comparisons without allowing automatic scientific PASS.
            row = rows[-1]
            row["rgb_beats_rb_swap"] = (
                values["rgb"] > values["rgb_rb_swapped"]
                if values["rgb"] is not None and values["rgb_rb_swapped"] is not None else None)
            row["rgb_beats_gray"] = (
                values["rgb"] > values["gray"]
                if values["rgb"] is not None and values["gray"] is not None else None)
            row["rgb_mean_rel_l2"] = scored["rgb"]["mean_assigned_relative_l2"]
            row["swap_mean_rel_l2"] = scored["rgb_rb_swapped"]["mean_assigned_relative_l2"]
            row["gray_mean_rel_l2"] = scored["gray"]["mean_assigned_relative_l2"]
            row["rgb_mean_abs_chroma"] = float(np.mean([
                proxies[str(sign)]["mean_abs_chroma"] for sign in SIGNS]))
            row["rgb_edge_chroma"] = float(np.mean([
                proxies[str(sign)]["edge_chroma_mean"] for sign in SIGNS]))
            row["rgb_saturated_fraction"] = float(np.mean([
                proxies[str(sign)]["saturated_channel_fraction"] for sign in SIGNS]))
            row["scope"] = "SYNTHETIC_DIRECTIONAL_TEMPLATE_SCORE_ONLY"
    valid = [row for row in rows if row["rgb_alignment"] is not None]
    summary = {
        "study": VERSION,
        "rows": len(rows),
        "scenes": list(scenes),
        "signed_delta_D": list(SIGNS),
        "profiles": [p.name for p in profiles],
        "optimizer_statuses": optimizers,
        "optimizers_all_success": all(
            r["gray_success"] and r["rgb_success"] for r in optimizers),
        "rgb_positive_alignment_count": sum(r["rgb_alignment"] > 0 for r in valid),
        "rgb_beats_channel_swap_count": sum(r["rgb_beats_rb_swap"] for r in valid),
        "rgb_beats_gray_count": sum(r["rgb_beats_gray"] for r in valid),
        "defined_directional_rows": len(valid),
        "median_rgb_alignment": median(r["rgb_alignment"] for r in valid) if valid else None,
        "median_rb_swap_alignment": median(r["rb_swap_alignment"] for r in valid) if valid else None,
        "median_gray_alignment": median(r["gray_alignment"] for r in valid) if valid else None,
        "verdict": "DIAGNOSTIC_ONLY_NO_ACCOMMODATION_CLAIM",
        "key_limitations": [
            "Alignment means template-distance orientation, not human accommodation direction",
            "Swapping R/B preserves RGB degrees and chroma amplitude, but is not an independently optimized null under the actual color mapping",
            "Grayscale optimized control has only 1/3 as many pixel variables",
            "R2 training and R3 scoring share scalar Fourier optics and an LCA equation",
            "Target retinal images are synthetic, not optically measured",
            "No display calibration, human accommodation, eye comfort, safety or clinical effect",
            "Each scene separately optimized; no universal transferable filter evaluated",
        ],
    }
    return rows, summary


def write_results(out: Path, rows: list[dict], summary: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "direction.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    files = {n: Path(__file__).resolve().parents[1] / n for n in (
        "r2_display_inverse/inverse.py",
        "r3_model_mismatch/alt_optics.py",
        "r3_model_mismatch/evaluate.py",
        "r4_directional_controls/evaluate.py",
    )}
    manifest = {
        "study": VERSION,
        "source_sha256": {name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for name, p in files.items()},
        "output_names": ["direction.csv", "summary.json", "manifest.json"],
        "data_class": "synthetic and exploratory; no measured accommodation",
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--size", type=int, default=64)
    parser.add_argument("--maxiter", type=int, default=90)
    args = parser.parse_args()
    rows, summary = run(size=args.size, maxiter=args.maxiter)
    write_results(args.out, rows, summary)
    print(json.dumps({
        "study": VERSION, "rows": summary["rows"],
        "rgb_positive_alignment_count": summary["rgb_positive_alignment_count"],
        "rgb_beats_channel_swap_count": summary["rgb_beats_channel_swap_count"],
        "rgb_beats_gray_count": summary["rgb_beats_gray_count"],
        "verdict": summary["verdict"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
