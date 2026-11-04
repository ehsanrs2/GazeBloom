#!/usr/bin/env python3
"""R1 model-audit and sensitivity sweep, constrained to existing Q1 surrogate.

This is an **in-silico** validation pipeline. It does not model display spectral
power distributions, gamma, clipping, ocular higher-order aberrations, or any
human accommodative response. Its 'improvement' concerns ONLY PSF error.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from hashlib import sha256
import itertools
import json
import math
from pathlib import Path
import platform
import sys
from statistics import median

import numpy as np

# Preserve the frozen original exploratory Q1 implementation unchanged.
LEGACY_DIR = Path(__file__).resolve().parents[1] / "waveoptics_q1_v1"
sys.path.insert(0, str(LEGACY_DIR))
from waveoptics_validation import (  # noqa: E402
    WAVELENGTH_NM,
    convolve_gaussian_psf,
    lca_diopters,
    model_psf,
    optimize_control,
    optimize_one,
)

MODEL_ID = "r1_waveoptics_surrogate_v1"
CHANNELS = ("R", "G", "B")
FIELDS = (
    "case_id", "distance_m", "pitch_mm", "pupil_mm", "delta_magnitude_D",
    "direction", "signed_delta_D", "baseline_error", "shared_error",
    "channel_error", "gain_vs_shared_percent", "gain_vs_baseline_percent",
    "shared_sigma_px", "red_sigma_px", "green_sigma_px", "blue_sigma_px",
    "channel_fit_le_shared", "scope",
)


@dataclass(frozen=True)
class Case:
    distance_m: float
    pitch_mm: float
    pupil_mm: float
    delta_magnitude_D: float

    def validate(self) -> None:
        ranges = {
            "distance_m": (0.3, 1.5),
            "pitch_mm": (0.12, 0.6),
            "pupil_mm": (2.0, 6.5),
            "delta_magnitude_D": (0.15, 0.85),
        }
        for field, (low, high) in ranges.items():
            value = getattr(self, field)
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{field} outside declared model range [{low}, {high}]")


def grid_for(preset: str) -> tuple[Case, ...]:
    if preset == "smoke":
        axes = ((0.6,), (0.27,), (3.0, 4.0), (0.45,))
    elif preset == "pilot":
        axes = ((0.5, 0.8), (0.24, 0.31), (3.0, 5.0), (0.3, 0.6))
    elif preset == "extended":
        axes = ((0.5, 0.6, 0.8), (0.20, 0.27, 0.34),
                (2.5, 4.0, 5.5), (0.20, 0.45, 0.75))
    else:
        raise ValueError(f"unknown preset: {preset}")
    result = tuple(Case(*axis) for axis in itertools.product(*axes))
    for case in result:
        case.validate()
    if len(set(result)) != len(result):
        raise AssertionError("duplicate grid case")
    return result


def checked_psf(defocus: float, wavelength: float, case: Case,
                *, n_fft: int = 320, subpixels: int = 7,
                kernel_size: int = 49) -> np.ndarray:
    arr = model_psf(
        defocus, wavelength,
        pupil_mm=case.pupil_mm,
        distance_m=case.distance_m,
        pitch_mm=case.pitch_mm,
        n_fft=n_fft,
        subpixels=subpixels,
        kernel_size=kernel_size,
    )
    if (arr.shape != (kernel_size, kernel_size)
            or not np.isfinite(arr).all() or arr.min() < -1e-12
            or abs(float(arr.sum()) - 1.0) > 1e-9):
        raise ValueError("nonphysical / malformed computed PSF")
    return arr


def aggregate_error(pred: dict[str, np.ndarray],
                    target: dict[str, np.ndarray]) -> float:
    """Normalized joint RGB PSF L2 error. Not an ocular response metric."""
    numerator = sum(float(np.sum((pred[c] - target[c]) ** 2))
                    for c in CHANNELS)
    denominator = sum(float(np.sum(target[c] ** 2)) for c in CHANNELS)
    if denominator <= 0:
        raise ValueError("zero target power")
    return math.sqrt(numerator / denominator)


def run_case(case: Case, case_id: int, *,
             n_fft: int = 320, subpixels: int = 7,
             kernel_size: int = 49) -> list[dict]:
    case.validate()
    baselines = {
        c: checked_psf(
            lca_diopters(WAVELENGTH_NM[c]), WAVELENGTH_NM[c], case,
            n_fft=n_fft, subpixels=subpixels, kernel_size=kernel_size,
        )
        for c in CHANNELS
    }
    rows: list[dict] = []
    # Algebraic signs only: they must not be interpreted as measured near/far focus.
    for direction, signed_delta in (("plus_delta", case.delta_magnitude_D),
                                    ("minus_delta", -case.delta_magnitude_D)):
        targets = {
            c: checked_psf(
                lca_diopters(WAVELENGTH_NM[c]) + signed_delta,
                WAVELENGTH_NM[c], case, n_fft=n_fft,
                subpixels=subpixels, kernel_size=kernel_size,
            )
            for c in CHANNELS
        }
        shared_sigma = optimize_control(baselines, targets)
        channel_sigmas = {
            c: optimize_one(baselines[c], targets[c]) for c in CHANNELS
        }
        shared = {
            c: convolve_gaussian_psf(baselines[c], shared_sigma)
            for c in CHANNELS
        }
        per_channel = {
            c: convolve_gaussian_psf(baselines[c], channel_sigmas[c])
            for c in CHANNELS
        }
        before = aggregate_error(baselines, targets)
        shared_error = aggregate_error(shared, targets)
        channel_error = aggregate_error(per_channel, targets)
        if not all(math.isfinite(v) for v in
                   (before, shared_error, channel_error, shared_sigma,
                    *channel_sigmas.values())):
            raise ValueError("nonfinite optimization result")
        rows.append({
            "case_id": case_id,
            **asdict(case),
            "direction": direction,
            "signed_delta_D": signed_delta,
            "baseline_error": before,
            "shared_error": shared_error,
            "channel_error": channel_error,
            "gain_vs_shared_percent": (
                100 * (1 - channel_error / shared_error)
                if shared_error > 1e-12 else None
            ),
            "gain_vs_baseline_percent": (
                100 * (1 - channel_error / before)
                if before > 1e-12 else None
            ),
            "shared_sigma_px": shared_sigma,
            "red_sigma_px": channel_sigmas["R"],
            "green_sigma_px": channel_sigmas["G"],
            "blue_sigma_px": channel_sigmas["B"],
            "channel_fit_le_shared": channel_error <= shared_error + 1e-6,
            "scope": "SIMULATED_PSF_ONLY",
        })
    return rows


def numerical_audit(case: Case) -> dict:
    """Descriptive convergence checks; no unvalidated tolerance = 'proof'."""
    case.validate()
    wavelengths = [WAVELENGTH_NM[c] for c in CHANNELS]
    errors = {}
    asymmetries = {}
    for c, wl in zip(CHANNELS, wavelengths):
        d = lca_diopters(wl)
        coarse = checked_psf(d, wl, case, n_fft=320)
        fine = checked_psf(d, wl, case, n_fft=480)
        errors[c] = float(
            np.linalg.norm(fine - coarse) / max(np.linalg.norm(fine), 1e-12)
        )
        asymmetries[c] = float(np.max(np.abs(coarse - coarse[::-1, ::-1])))
    return {
        "comparison": "320-vs-480 FFT samples, same pupil window and output grid",
        "baseline_rel_l2_disagreement": errors,
        "centrosymmetry_max_abs": asymmetries,
        "status": "DESCRIPTIVE_NUMERICAL_DIAGNOSTIC_NOT_A_MEASUREMENT",
    }


def make_summary(rows: list[dict], audit: dict, grid: tuple[Case, ...],
                 *, preset: str) -> dict:
    valid = [r for r in rows if r["gain_vs_shared_percent"] is not None]
    gains = [r["gain_vs_shared_percent"] for r in valid]
    residuals = [r["channel_error"] for r in rows]
    return {
        "model_id": MODEL_ID,
        "preset": preset,
        "cases": len(grid),
        "direction_rows": len(rows),
        "fit_advantage_cases": sum(r["channel_fit_le_shared"] for r in rows),
        "shared_comparison_explanation": (
            "RGB-specific blur has three free sigmas versus one shared sigma. "
            "Better fit is expected even with no real accommodation effect."
        ),
        "channel_residual_l2": {
            "min": min(residuals), "median": median(residuals),
            "max": max(residuals),
        },
        "fit_gain_vs_shared_percent": {
            "min": min(gains), "median": median(gains),
            "max": max(gains),
        } if gains else None,
        "audit": audit,
        "numerical_claim": "MODEL_INTERNAL_COMPARISONS_ONLY",
        "human_accommodation_claim": "NOT_MEASURED",
        "eye_strain_or_clinical_claim": "NOT_MEASURED",
        "untested_factors": [
            "individual wavefront and aberrations", "display spectral power distribution",
            "gamma/luminance and pixel substructure", "display clipping and deconvolution",
            "off-axis viewing", "pupil dynamics", "accommodative adaptation",
            "human comfort, safety and treatment efficacy",
        ],
    }


def write_output(out: Path, grid: tuple[Case, ...], rows: list[dict],
                 summary: dict, *, preset: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "sweep.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                k: (""
                    if row.get(k) is None else row[k])
                for k in FIELDS
            })
    (out / "summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    legacy = LEGACY_DIR / "waveoptics_validation.py"
    here = Path(__file__).resolve()
    manifest = {
        "schema_version": "1.0",
        "preset": preset,
        "cases": [asdict(c) for c in grid],
        "legacy_model_sha256": sha256(legacy.read_bytes()).hexdigest(),
        "runner_sha256": sha256(here.read_bytes()).hexdigest(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "algorithm": "wave-optics PSF plus constrained positive Gaussian blurs",
        "output_files": ["sweep.csv", "summary.json", "manifest.json",
                         "fit_summary.png"],
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    # A visual summary that never describes these errors as biological effects.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    labels = [f"{r['case_id']}:{'+' if r['signed_delta_D'] > 0 else '-'}"
              for r in rows]
    fig, ax = plt.subplots(figsize=(max(8, len(rows) * 0.24), 5))
    index = np.arange(len(rows))
    width = 0.28
    ax.bar(index - width, [r["baseline_error"] for r in rows],
           width=width, label="Unmodified screen PSF")
    ax.bar(index, [r["shared_error"] for r in rows],
           width=width, label="Shared-RGB Gaussian")
    ax.bar(index + width, [r["channel_error"] for r in rows],
           width=width, label="Per-channel Gaussian")
    ax.set_xticks(index, labels, rotation=90, fontsize=8)
    ax.set_xlabel("Sensitivity case ID / signed defocus direction")
    ax.set_ylabel("Normalized joint RGB PSF L2 residual (lower fits better)")
    ax.set_title("GazeBloom R1 — computational surrogate ONLY, not eye data")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "fit_summary.png", dpi=120)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=("smoke", "pilot", "extended"),
                        default="smoke")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    grid = grid_for(args.preset)
    rows = [row for i, case in enumerate(grid, start=1)
            for row in run_case(case, i)]
    audit = numerical_audit(grid[0])
    summary = make_summary(rows, audit, grid, preset=args.preset)
    write_output(args.out, grid, rows, summary, preset=args.preset)
    print(json.dumps({
        "model_id": MODEL_ID, "preset": args.preset, "cases": len(grid),
        "direction_rows": len(rows), "residual_l2": summary["channel_residual_l2"],
        "gain_vs_shared_percent": summary["fit_gain_vs_shared_percent"],
        "numerical_audit": audit["baseline_rel_l2_disagreement"],
        "status": "SIMULATION_ONLY_NO_HUMAN_OUTCOME",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
