#!/usr/bin/env python3
"""R2: bounded linear-light display-image inversion (simulation only).

Assumes a monochromatic primary per RGB channel, a *fixed* accommodative
state and spatially invariant circular convolution. No measured monitor, eye,
medical benefit, or replication of Cholewiak et al. 2018 is claimed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.optimize import minimize

LEGACY_DIR = Path(__file__).resolve().parents[1] / "waveoptics_q1_v1"
sys.path.insert(0, str(LEGACY_DIR))
from waveoptics_validation import WAVELENGTH_NM, lca_diopters, model_psf  # noqa: E402

CHANNELS = ("R", "G", "B")
MODEL = "R2_SIMULATED_BOUNDED_RGB_INVERSION_V1"


def scene_pattern(n: int, seed: int = 812) -> np.ndarray:
    """A reproducible high- and low-spatial-frequency achromatic scene."""
    if n < 32 or n % 2:
        raise ValueError("scene size must be even and >=32")
    y, x = np.mgrid[:n, :n]
    rng = np.random.default_rng(seed)
    shape = (0.32 * (x > n // 2) + 0.15 * (y > n // 3)
             + 0.11 * ((x // 8 + y // 8) % 2)
             + 0.09 * np.sin(2 * np.pi * (x + y / 2) / 18)
             + 0.05 * rng.normal(size=(n, n)))
    return np.clip(0.18 + shape, 0.08, 0.92).astype(np.float64)


def psf_otf(psf: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Map an odd, centered PSF to circular-convolution frequency domain."""
    kh, kw = psf.shape
    h, w = shape
    if kh % 2 == 0 or kw % 2 == 0 or kh > h or kw > w:
        raise ValueError("PSF must be odd and fit inside image")
    if not np.isfinite(psf).all() or psf.min() < 0 or not np.isclose(psf.sum(), 1, atol=1e-9):
        raise ValueError("PSF must be nonnegative, normalized, finite")
    padded = np.zeros(shape)
    padded[:kh, :kw] = psf
    padded = np.roll(padded, shift=(-(kh // 2), -(kw // 2)), axis=(0, 1))
    return np.fft.rfft2(padded)


def forward(images: np.ndarray, otfs: np.ndarray) -> np.ndarray:
    """Periodic convolution: appropriate only for a tiled stimulus crop."""
    if images.shape[0] != 3 or otfs.shape[0] != 3:
        raise ValueError("RGB arrays required")
    return np.fft.irfft2(np.fft.rfft2(images, axes=(-2, -1)) * otfs,
                         s=images.shape[-2:], axes=(-2, -1))


def retinal_relative_error(pred: np.ndarray, target: np.ndarray) -> float:
    return float(np.linalg.norm(pred - target) / max(np.linalg.norm(target), 1e-12))


def objective(flat: np.ndarray, otfs: np.ndarray, target: np.ndarray,
              source: np.ndarray, *, shared: bool,
              lambda_deviation: float, lambda_chroma: float) -> tuple[float, np.ndarray]:
    n = source.size
    x = flat.reshape((1 if shared else 3,) + source.shape)
    rgb = np.broadcast_to(x, (3,) + source.shape)
    pred = forward(rgb, otfs)
    residual = pred - target
    scale = 3 * n
    loss = 0.5 * float(np.sum(residual ** 2)) / scale
    grad = np.fft.irfft2(np.fft.rfft2(residual, axes=(-2, -1)) *
                         np.conj(otfs), s=source.shape, axes=(-2, -1)) / scale
    dx = rgb - source[None]
    loss += lambda_deviation * 0.5 * float(np.sum(dx ** 2)) / scale
    grad = grad + lambda_deviation * dx / scale
    chroma = rgb - rgb.mean(axis=0, keepdims=True)
    loss += lambda_chroma * 0.5 * float(np.sum(chroma ** 2)) / scale
    grad = grad + lambda_chroma * chroma / scale
    if shared:
        grad = grad.sum(axis=0, keepdims=True)
    return float(loss), np.ascontiguousarray(grad).reshape(-1)


def optimize_display(otfs: np.ndarray, target: np.ndarray,
                     source: np.ndarray, *, shared: bool = False,
                     lambda_deviation: float = 0.002,
                     lambda_chroma: float = 0.01,
                     maxiter: int = 90) -> tuple[np.ndarray, dict]:
    if min(lambda_deviation, lambda_chroma) < 0 or maxiter < 1:
        raise ValueError("regularizers must be nonnegative and iterations positive")
    start = np.broadcast_to(source, (1 if shared else 3,) + source.shape).copy()

    def fun(v: np.ndarray) -> tuple[float, np.ndarray]:
        return objective(v, otfs, target, source, shared=shared,
                         lambda_deviation=lambda_deviation,
                         lambda_chroma=lambda_chroma)

    result = minimize(fun, start.ravel(), method="L-BFGS-B", jac=True,
                      bounds=[(0., 1.)] * start.size,
                      options={"maxiter": maxiter, "ftol": 1e-10, "gtol": 1e-8})
    x = result.x.reshape(start.shape)
    rgb = np.broadcast_to(x, (3,) + source.shape).copy()
    if not np.isfinite(rgb).all() or rgb.min() < -1e-12 or rgb.max() > 1 + 1e-12:
        raise AssertionError("display constraint violation")
    return rgb, {"optimizer_success": bool(result.success),
                 "message": str(result.message),
                 "iterations": int(result.nit), "objective": float(result.fun)}


def optical_otfs(pupil_mm: float, delta_D: float, *, size: int,
                 distance_m: float = 0.6, pitch_mm: float = 0.27,
                 n_fft: int = 320) -> tuple[np.ndarray, np.ndarray]:
    """Fixed-eye baseline vs hypothetical shifted-depth target PSFs."""
    if not 2 <= pupil_mm <= 6.5 or not -0.85 <= delta_D <= 0.85:
        raise ValueError("pupil/delta beyond exploratory model limits")
    base, target = [], []
    for channel in CHANNELS:
        wl = WAVELENGTH_NM[channel]
        ref = lca_diopters(wl)
        b = model_psf(ref, wl, pupil_mm=pupil_mm, distance_m=distance_m,
                      pitch_mm=pitch_mm, n_fft=n_fft)
        t = model_psf(ref + delta_D, wl, pupil_mm=pupil_mm,
                      distance_m=distance_m, pitch_mm=pitch_mm, n_fft=n_fft)
        base.append(psf_otf(b, (size, size)))
        target.append(psf_otf(t, (size, size)))
    return np.stack(base), np.stack(target)


def encode_decode_8bit(linear_rgb: np.ndarray, *,
                       encode_gamma: float = 2.2,
                       actual_gamma: float = 2.2) -> np.ndarray:
    if encode_gamma <= 0 or actual_gamma <= 0:
        raise ValueError("gamma must be positive")
    encoded = np.rint(255 * np.clip(linear_rgb, 0, 1) ** (1 / encode_gamma)) / 255
    return encoded ** actual_gamma


def evaluate(pupil_mm: float = 4., delta_D: float = 0.45,
             n: int = 64, maxiter: int = 90,
             *, distance_m: float = 0.6, pitch_mm: float = 0.27) -> tuple[dict, dict]:
    scene = scene_pattern(n)
    base_otf, target_otf = optical_otfs(pupil_mm, delta_D, size=n,
                                        distance_m=distance_m, pitch_mm=pitch_mm)
    initial = np.repeat(scene[None], 3, axis=0)
    target = forward(initial, target_otf)
    shared, shared_status = optimize_display(base_otf, target, scene, shared=True,
                                             maxiter=maxiter)
    rgb, rgb_status = optimize_display(base_otf, target, scene, shared=False,
                                       maxiter=maxiter)
    alternatives = {"unmodified": initial, "shared": shared, "rgb": rgb}
    metrics = {}
    for name, display in alternatives.items():
        predicted = forward(display, base_otf)
        linear = retinal_relative_error(predicted, target)
        sample8 = encode_decode_8bit(display)
        quantized = retinal_relative_error(forward(sample8, base_otf), target)
        gamma_mismatch = {
            str(g): retinal_relative_error(forward(
                encode_decode_8bit(display, actual_gamma=g), base_otf), target)
            for g in (2.0, 2.4)
        }
        metrics[name] = {
            "retinal_image_rel_l2": linear,
            "retinal_image_8bit_gamma22_rel_l2": quantized,
            "gamma_mismatch_rel_l2": gamma_mismatch,
            "display_min": float(display.min()), "display_max": float(display.max()),
            "clipped_pixels_fraction": float(np.mean((display <= 1e-9) | (display >= 1 - 1e-9))),
            "mean_abs_rgb_difference": float(np.mean(np.abs(display - display.mean(axis=0)))),
        }
    holdouts = {}
    for offset in (-0.5, +0.5):
        other = pupil_mm + offset
        if not 2 <= other <= 6.5:
            continue
        h_base, h_target = optical_otfs(other, delta_D, size=n,
                                        distance_m=distance_m, pitch_mm=pitch_mm)
        other_t = forward(initial, h_target)
        holdouts[str(other)] = {
            name: retinal_relative_error(forward(display, h_base), other_t)
            for name, display in alternatives.items()
        }
    summary = {
        "model": MODEL, "scope": "COMPUTATIONAL_ONLY_NOT_EYE_MEASUREMENT",
        "scene_size": n, "pupil_mm": pupil_mm, "delta_D": delta_D,
        "distance_m": distance_m, "pitch_mm": pitch_mm,
        "n_fft": 320, "image_boundary": "circular_periodic_tiled_crop",
        "display_domain": "ideal_linear_light_RGB_each_channel_[0,1]",
        "display_spectrum": "monochromatic_assumed_peaks_not_measured",
        "metrics": metrics, "holdout_pupil_errors": holdouts,
        "optimizer": {"shared": shared_status, "rgb": rgb_status},
        "objective_caution": "Unregularized retinal L2 scored on same surrogate as optimization; inverse crime risk",
        "physiology": "NOT_MEASURED", "eye_strain_relief": "NOT_MEASURED",
    }
    return summary, {"scene": scene, "unmodified": initial, "shared": shared,
                     "rgb": rgb, "target": target,
                     "predicted_unmodified": forward(initial, base_otf),
                     "predicted_shared": forward(shared, base_otf),
                     "predicted_rgb": forward(rgb, base_otf)}


def write_results(out: Path, summary: dict, images: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    np.savez_compressed(out / "arrays.npz", **images)
    from PIL import Image, ImageDraw
    tiles = ["unmodified", "shared", "rgb", "target", "predicted_unmodified",
             "predicted_shared", "predicted_rgb"]
    canvas = Image.new("RGB", (512 * 4, 512 * 2), "white")
    draw = ImageDraw.Draw(canvas)
    for index, label in enumerate(tiles):
        data = images[label]
        if data.ndim == 2:
            data = np.repeat(data[None], 3, axis=0)
        # Display simulated *linear* RGB using assumed gamma 2.2 only.
        encoded = np.clip(data, 0, 1) ** (1 / 2.2)
        pixels = np.asarray(np.clip(encoded * 255, 0, 255), dtype=np.uint8).transpose(1, 2, 0)
        img = Image.fromarray(pixels).resize((500, 470), Image.Resampling.NEAREST)
        x, y = (index % 4) * 512, (index // 4) * 512
        canvas.paste(img, (x, y + 30))
        draw.text((x + 4, y + 8), label, fill="black")
    canvas.save(out / "comparison.png")
    script = Path(__file__).resolve()
    manifest = {"model": MODEL, "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
                "outputs": ["summary.json", "arrays.npz", "comparison.png"],
                "claims": "SIMULATION_ONLY"}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pupil-mm", type=float, default=4.)
    parser.add_argument("--delta-D", type=float, default=0.45)
    parser.add_argument("--size", type=int, default=64)
    parser.add_argument("--maxiter", type=int, default=90)
    args = parser.parse_args()
    summary, images = evaluate(args.pupil_mm, args.delta_D, args.size, args.maxiter)
    write_results(args.out, summary, images)
    print(json.dumps({"model": MODEL, "pupil_mm": args.pupil_mm, "delta_D": args.delta_D,
                      "metrics": {k: round(v["retinal_image_rel_l2"], 5)
                                  for k, v in summary["metrics"].items()},
                      "physiology": "NOT_MEASURED"}, sort_keys=True))


if __name__ == "__main__":
    main()
