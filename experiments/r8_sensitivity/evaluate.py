#!/usr/bin/env python3
"""R8 preregistered sensitivity grid for synthetic template-free focus proxies.

This is a falsification/sensitivity study, not a physical calibration,
human accommodation model, visual exercise, or clinical efficacy experiment.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import sys

import numpy as np

EXPERIMENTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXPERIMENTS.parent))
sys.path.insert(0, str(EXPERIMENTS / "r3_model_mismatch"))
sys.path.insert(0, str(EXPERIMENTS / "r5_equal_capacity_controls"))

from experiments.r3_model_mismatch.alt_optics import (  # noqa: E402
    RGB_PEAKS_NM, ForwardProfile, centered_otf, code_to_light,
    mix_channels, optical_forward, optics_otfs, spectral_psf,
    validation_profiles,
)
from experiments.r3_model_mismatch.evaluate import make_scene  # noqa: E402
from experiments.r5_equal_capacity_controls.evaluate import MODELS  # noqa: E402
from experiments.r6_identifiability.evaluate import (  # noqa: E402
    SIGNS, TARGET_GENERATOR, cross_generated_fit, match_scene_pair,
)

STUDY = "R8_FOCUS_METRIC_SPECTRAL_UNCERTAINTY_V1"
SCENES = ("original_texture", "synthetic_letter_edges",
          "radial_rings", "oblique_gratings")
METRICS = ("gradient", "laplacian", "bandpass")
FINE_FOCUS_D = tuple(-.75 + .0625*i for i in range(25))
STRIDES = (4, 2, 1)  # 0.25, 0.125, 0.0625 D, all nested on same optics
# Chosen before R8 outcome; these are numerical curve-shape heuristics,
# not measurement uncertainty, psychophysics, or confidence intervals.
PEAK_TIE_REL = .002
CURVE_FLAT_REL = .01
ASSUMED_LUMINANCE = (.2126, .7152, .0722)


@dataclass(frozen=True)
class SpectralCase:
    name: str
    halfwidth_nm: float
    peak_shifts_nm: tuple[float, float, float]
    gamma: float
    def profile(self) -> ForwardProfile:
        return ForwardProfile(
            name=self.name, spectral_halfwidth_nm=self.halfwidth_nm,
            astig_opd_um=.10, coma_opd_um=.05, gamma_actual=self.gamma,
            channel_leakage=0.,
        )


# A SMALL, fixed synthetic uncertainty grid, NOT sampled display SPDs.
CASES = (
    SpectralCase("narrow8_gamma22", 8., (0., 0., 0.), 2.2),
    SpectralCase("wide28_gamma22", 28., (0., 0., 0.), 2.2),
    SpectralCase("shifted8_gamma22", 18., (+8., -6., +8.), 2.2),
    SpectralCase("wide28_gamma24", 28., (0., 0., 0.), 2.4),
)


def make_r8_scene(name: str, n: int) -> np.ndarray:
    if name in ("original_texture", "synthetic_letter_edges"):
        return make_scene(name, n)
    y, x = np.indices((n, n), dtype=float)
    if name == "radial_rings":
        r = np.hypot(x - (n-1)/2, y - (n-1)/2)
        image = .52 + .22*np.cos(2*np.pi*r/11) + .12*np.cos(2*np.pi*r/4.8)
    elif name == "oblique_gratings":
        image = (.50
                 + .22*np.cos(2*np.pi*(5*x + 2*y)/n)
                 + .17*np.cos(2*np.pi*(3*x - 9*y)/n))
    else:
        raise ValueError("unknown frozen scene")
    return np.clip(image, .05, .95)


@lru_cache(maxsize=160)
def shifted_otfs(case: SpectralCase, focus_D: float, n: int) -> np.ndarray:
    """Channel OTFs under hypothetical primary spectra/center shifts.

    Uses the same R3 toy scalar diffraction engine throughout.
    Does NOT infer the spectra of any real monitor.
    """
    p = case.profile()
    if case.peak_shifts_nm == (0., 0., 0.):
        return optics_otfs(p, focus_D, n)[1]
    otfs = []
    for peak, shift in zip(RGB_PEAKS_NM, case.peak_shifts_nm):
        psf = spectral_psf(peak + shift, focus_D, p)
        otfs.append(centered_otf(psf, (n, n)))
    return np.stack(otfs)


def focus_metrics(luminance: np.ndarray) -> dict[str, float]:
    """Three non-clinical image autofocus objective functions.

    All use the *same* modeled luminance image. Periodic sampling matches
    the R3 circular convolution setup. Higher is taken as "sharper" by
    convention, not as proof of eye focusing behavior.
    """
    if luminance.ndim != 2 or not np.isfinite(luminance).all():
        raise ValueError("finite 2D luminance required")
    gx = (np.roll(luminance, -1, 1)-np.roll(luminance, 1, 1))*.5
    gy = (np.roll(luminance, -1, 0)-np.roll(luminance, 1, 0))*.5
    lap = (np.roll(luminance, 1, 0) + np.roll(luminance, -1, 0)
           + np.roll(luminance, 1, 1) + np.roll(luminance, -1, 1)
           - 4*luminance)
    h,w = luminance.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.rfftfreq(w)[None, :]
    radius = np.sqrt(fy*fy+fx*fx)
    band = (radius >= .08) & (radius <= .25)
    spectrum = np.abs(np.fft.rfft2(luminance))**2
    return {
        "gradient": float(np.mean(gx*gx + gy*gy)),
        "laplacian": float(np.mean(lap*lap)),
        "bandpass": float(np.sum(spectrum[band])/(h*w)**2),
    }


def describe_peak(minus: np.ndarray, plus: np.ndarray,
                  focus_grid: np.ndarray) -> dict:
    """Frozen peak stability criteria; invalid peaks become NULL results."""
    if minus.ndim != 1 or plus.shape != minus.shape or minus.size != focus_grid.size:
        raise ValueError("focus curves and grid must be equal 1D arrays")
    if minus.size < 3 or not np.all(np.diff(focus_grid)>0):
        raise ValueError("invalid increasing focus grid")
    if not (np.isfinite(minus).all() and np.isfinite(plus).all()):
        raise ValueError("nonfinite focus scores")
    if (minus < -1e-12).any() or (plus < -1e-12).any():
        raise ValueError("sharpness scores must be nonnegative")
    def peak(y):
        index = int(np.argmax(y))
        scale = max(float(np.mean(y)), 1e-14)
        ranked = np.sort(y)
        prominence = float((ranked[-1]-ranked[-2])/scale)
        span = float((ranked[-1]-ranked[0])/scale)
        if index in (0,y.size-1):
            status="ABSTAIN_BOUNDARY"
        elif span <= CURVE_FLAT_REL:
            status="ABSTAIN_FLAT"
        elif prominence <= PEAK_TIE_REL:
            status="ABSTAIN_NEAR_TIE"
        else:
            status="RESOLVED"
        return index, status, prominence, span
    mi,ms,mp,span_m = peak(minus)
    pi,ps,pp,span_p = peak(plus)
    raw_delta = float(focus_grid[pi]-focus_grid[mi])
    return {
        "raw_delta_peak_D": raw_delta,
        "reportable_delta_peak_D": raw_delta if ms=="RESOLVED" and ps=="RESOLVED" else None,
        "minus_peak_D": float(focus_grid[mi]),
        "plus_peak_D": float(focus_grid[pi]),
        "minus_status": ms, "plus_status": ps,
        "min_peak_prominence_rel": min(mp,pp),
        "min_curve_span_rel": min(span_m,span_p),
        "curve_difference_rel": float(
            np.sqrt(np.mean((minus-plus)**2))
            / max(.5*float(minus.mean()+plus.mean()),1e-14)
        ),
    }


def focus_curves(images: dict, case: SpectralCase, n: int) -> tuple[dict,dict]:
    """Evaluate RGB and all-common-green optical control, no target templates.

    Uses R6 matched images. Gamma encoding is intentionally applied in
    *both* branches, so nonlinear EOTF is not mistaken for measured calibration.
    """
    profile = case.profile()
    decoded = {
        (arm,sign): code_to_light(images[arm][sign],case.gamma)
        for arm in MODELS for sign in SIGNS
    }
    curves = {
        (arm,sign,metric): [] for arm in MODELS
        for sign in SIGNS for metric in METRICS
    }
    controls = {k: [] for k in curves}
    weights = np.asarray(ASSUMED_LUMINANCE)
    for focus in FINE_FOCUS_D:
        otfs = shifted_otfs(case,focus,n)
        null_otfs = np.broadcast_to(otfs[1:2],otfs.shape)
        for arm in MODELS:
            for sign in SIGNS:
                light=decoded[(arm,sign)]
                retina = mix_channels(
                    optical_forward(light,otfs),profile.channel_leakage)
                null_retina = mix_channels(
                    optical_forward(light,null_otfs),profile.channel_leakage)
                measured=focus_metrics(np.einsum("c,chw->hw",weights,retina))
                null=focus_metrics(np.einsum("c,chw->hw",weights,null_retina))
                for metric in METRICS:
                    curves[(arm,sign,metric)].append(measured[metric])
                    controls[(arm,sign,metric)].append(null[metric])
    return curves,controls


def execute(*, scenes=SCENES,cases=CASES, size=64,maxiter=90):
    if not scenes or not cases or size<50 or size%2 or maxiter<1:
        raise ValueError("invalid study configuration")
    if len(set(scenes))!=len(scenes) or len(set(c.name for c in cases))!=len(cases):
        raise ValueError("frozen labels must be unique")
    generator=next(p for p in validation_profiles() if p.name==TARGET_GENERATOR)
    rows, statuses, matching=[],[],[]
    for scene_name in scenes:
        scene=make_r8_scene(scene_name,size)
        fitted, fit_info = cross_generated_fit(
            scene,generator=generator,maxiter=maxiter)
        matched,match_info=match_scene_pair(scene,fitted)
        statuses.extend({"scene":scene_name,**v} for v in fit_info)
        matching.append({"scene":scene_name,**match_info})
        for case in cases:
            curves,null_curves=focus_curves(matched,case,size)
            for arm in MODELS:
                for metric in METRICS:
                    for stride in STRIDES:
                        grid=np.asarray(FINE_FOCUS_D[::stride])
                        minus=np.asarray(curves[(arm,SIGNS[0],metric)][::stride])
                        plus=np.asarray(curves[(arm,SIGNS[1],metric)][::stride])
                        null_minus=np.asarray(null_curves[(arm,SIGNS[0],metric)][::stride])
                        null_plus=np.asarray(null_curves[(arm,SIGNS[1],metric)][::stride])
                        peak=describe_peak(minus,plus,grid)
                        null=describe_peak(null_minus,null_plus,grid)
                        rows.append({
                            "scene":scene_name,"spectral_case":case.name,
                            "peak_offsets_nm":list(case.peak_shifts_nm),
                            "spectrum_halfwidth_nm":case.halfwidth_nm,
                            "gamma_actual":case.gamma,
                            "arm":arm,"metric":metric,
                            "step_D":float(grid[1]-grid[0]),
                            "n_focus":int(grid.size),
                            **peak,
                            "common_psf_raw_delta_peak_D":null["raw_delta_peak_D"],
                            "common_psf_reportable_delta_peak_D":null["reportable_delta_peak_D"],
                            "common_psf_minus_status":null["minus_status"],
                            "common_psf_plus_status":null["plus_status"],
                            "common_psf_curve_difference_rel":null["curve_difference_rel"],
                            "evidence_scope":"SYNTHETIC_AUTOFOCUS_SENSITIVITY_NOT_ACCOMMODATION",
                        })
    by_step_metric={}
    for metric in METRICS:
        for stride in STRIDES:
            step=FINE_FOCUS_D[stride]-FINE_FOCUS_D[0]
            sub=[r for r in rows if r["metric"]==metric
                 and np.isclose(r["step_D"],step)]
            by_step_metric[f"{metric}_{step:.4f}"]={
                "rows":len(sub),
                "reportable":sum(r["reportable_delta_peak_D"] is not None for r in sub),
                "nonzero_reportable":sum(
                    r["reportable_delta_peak_D"] is not None
                    and abs(r["reportable_delta_peak_D"])>1e-12 for r in sub),
                "nonzero_raw":sum(abs(r["raw_delta_peak_D"])>1e-12 for r in sub),
                "control_reportable":sum(
                    r["common_psf_reportable_delta_peak_D"] is not None for r in sub),
                "control_nonzero_raw":sum(
                    abs(r["common_psf_raw_delta_peak_D"])>1e-12 for r in sub),
            }
    summary={
        "study":STUDY,"rows":len(rows),"scenes":list(scenes),
        "spectrum_cases":[c.__dict__ for c in cases],
        "metrics":list(METRICS),
        "focus_grid":list(FINE_FOCUS_D),
        "steps_D":[float(FINE_FOCUS_D[s]-FINE_FOCUS_D[0]) for s in STRIDES],
        "peak_criterion":{"relative_second_best_gap":PEAK_TIE_REL,
                          "minimum_relative_span":CURVE_FLAT_REL,
                          "abstain_boundary":True,
                          "not_confidence_or_human_noise":True},
        "training_generator":generator.name,
        "fitting_status":statuses,
        "all_optimizers_success":all(r["success"] for r in statuses),
        "matching":matching,
        "sensitivity_cells":by_step_metric,
        "overall_reportable":sum(r["reportable_delta_peak_D"] is not None for r in rows),
        "overall_nonzero_reportable":sum(
            r["reportable_delta_peak_D"] is not None
            and abs(r["reportable_delta_peak_D"])>1e-12 for r in rows),
        "overall_common_psf_nonzero_raw":sum(
            abs(r["common_psf_raw_delta_peak_D"])>1e-12 for r in rows),
        "interpretation":"EXPLORATORY_SYNTHETIC_NUMERICAL_SENSITIVITY_ONLY",
        "important_caveats":[
            "All focus measures are assumptions of algorithmic autofocus, not human eye behavior",
            "Three metrics and three grids yield correlated comparisons, not independent biological replicates",
            "Toy SPD 3-wavelength primaries; altered widths/shifts and gamma are synthetic not measured",
            "The gamma24 and shifted-primary controls are not a full factorial design",
            "R6 chroma/luminance balancing and R3 scalar optics are imperfect model-family assumptions",
            "Strong green-OTF common control removes all interchannel PSF variation, not just LCA",
            "Peak-threshold rules are numeric heuristics, not biological or inferential significance",
            "No physical monitor data, eye wavefront, autorefractor or human eye-strain outcomes",
        ]
    }
    return rows,summary


def write_outputs(out:Path,rows:list[dict],summary:dict)->None:
    out.mkdir(parents=True,exist_ok=True)
    with (out/"sensitivity.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out/"summary.json").write_text(
        json.dumps(summary,sort_keys=True,indent=2,ensure_ascii=False)+"\n",
        encoding="utf-8")
    scripts={name:EXPERIMENTS/name for name in (
        "r3_model_mismatch/alt_optics.py",
        "r3_model_mismatch/evaluate.py",
        "r5_equal_capacity_controls/evaluate.py",
        "r6_identifiability/evaluate.py",
        "r7_metric_validation/evaluate.py",
        "r8_sensitivity/evaluate.py")}
    (out/"manifest.json").write_text(json.dumps({
        "study":STUDY,
        "code_sha256":{k:sha256(v.read_bytes()).hexdigest() for k,v in scripts.items()},
        "output_files":["sensitivity.csv","summary.json","manifest.json"],
        "display_spd_measured":False,"human_accommodation_measured":False,
    },sort_keys=True,indent=2)+"\n",encoding="utf-8")


def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--size",type=int,default=64)
    p.add_argument("--maxiter",type=int,default=90)
    args=p.parse_args()
    rows,summary=execute(size=args.size,maxiter=args.maxiter)
    write_outputs(args.out,rows,summary)
    print(json.dumps({
        "study":STUDY,"rows":summary["rows"],
        "reportable":summary["overall_reportable"],
        "nonzero_reportable":summary["overall_nonzero_reportable"],
        "common_psf_nonzero_raw":summary["overall_common_psf_nonzero_raw"],
        "scope":summary["interpretation"]
    },sort_keys=True))


if __name__=="__main__":
    main()
