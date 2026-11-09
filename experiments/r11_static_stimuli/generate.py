#!/usr/bin/env python3
"""Generate *unapproved* static, mild RGB candidate/control image pairs.

This code intentionally DOES NOT present stimuli, collect participant data,
claim safety, or attempt to measure human accommodation.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, __version__ as PIL_VERSION

STUDY = "GAZEBLOOM_R11_STATIC_PAIRED_STIMULUS_PREFLIGHT_V1"
SCENES = ("NOVA", "LUMA", "MIRA", "TORA")
SIZE = (640, 360)
FONT_SIZE = 82
L_BACKGROUND = .54
L_FOREGROUND = .37
CHROMA_STRENGTH = .045
MODEL_LINEAR_WEIGHTS = np.asarray((.2126, .7152, .0722))
MAX_PROXY_LUMINANCE_MISMATCH = .008
MAX_SRGB_CHANNEL_SPREAD = 11
MAX_LINEAR_PIXEL_STEP = .23
MIN_CHANGED_PIXELS = 2000
CONDITIONS = ("X", "Y")


def linear_to_srgb(values: np.ndarray) -> np.ndarray:
    """IEC-style sRGB transfer assumption, NOT a measured monitor EOTF."""
    a = np.asarray(values, dtype=float)
    if not np.isfinite(a).all() or (a < 0).any() or (a > 1).any():
        raise ValueError("model linear light outside [0,1]")
    return np.where(a <= .0031308, 12.92*a,
                    1.055*np.power(a, 1/2.4) - .055)


def srgb_to_linear(values: np.ndarray) -> np.ndarray:
    a = np.asarray(values, dtype=float)
    if not np.isfinite(a).all() or (a < 0).any() or (a > 1).any():
        raise ValueError("sRGB input outside [0,1]")
    return np.where(a <= .04045, a/12.92,
                    np.power((a+.055)/1.055, 2.4))


def label_mask(word: str) -> Image.Image:
    """Large isolated word: avoid stripes, grids, dense patches and animations."""
    if word not in SCENES:
        raise ValueError("only preregistered four-word scenes are allowed")
    mask = Image.new("L", SIZE, color=0)
    draw = ImageDraw.Draw(mask)
    # Pillow-bundled font: no external downloaded or user-supplied font.
    font = ImageFont.load_default(size=FONT_SIZE)
    bounds = draw.textbbox((0, 0), word, font=font)
    x = (SIZE[0] - (bounds[2]-bounds[0]))//2 - bounds[0]
    y = (SIZE[1] - (bounds[3]-bounds[1]))//2 - bounds[1]
    draw.text((x, y), word, fill=255, font=font)
    return mask.filter(ImageFilter.GaussianBlur(radius=.9))


def generate_pair(word: str) -> tuple[np.ndarray, np.ndarray, dict]:
    """Two still images with equal intended linear-light luminance.

    X: achromatic; Y: weak red/green opponent component localized to
    large glyph edges. Model luminance is conserved before PNG quantization,
    not certified to be isoluminant on any physical monitor.
    """
    mask = label_mask(word)
    region = np.asarray(mask, dtype=np.float64)/255.
    model_luminance = L_BACKGROUND + (L_FOREGROUND-L_BACKGROUND)*region
    wide = np.asarray(mask.filter(ImageFilter.GaussianBlur(9)),dtype=np.float64)/255.
    near = np.asarray(mask.filter(ImageFilter.GaussianBlur(2)),dtype=np.float64)/255.
    color_field = CHROMA_STRENGTH * (near-wide)
    neutral = np.repeat(model_luminance[..., None], 3, axis=-1)
    colored = np.stack((
        model_luminance+color_field,
        model_luminance-color_field * float(MODEL_LINEAR_WEIGHTS[0]/MODEL_LINEAR_WEIGHTS[1]),
        model_luminance,
    ),axis=-1)
    # Fail, do not silently clamp or accept an out-of-gamut design.
    if min(float(neutral.min()),float(colored.min())) < 0 or max(float(neutral.max()),float(colored.max())) > 1:
        raise ValueError("out-of-gamut source design")

    def quantize(linear):
        return np.rint(linear_to_srgb(linear)*255).astype(np.uint8)
    x, y = quantize(neutral), quantize(colored)
    decoded_x = srgb_to_linear(x.astype(np.float64)/255.)
    decoded_y = srgb_to_linear(y.astype(np.float64)/255.)
    lx = np.einsum("hwc,c->hw",decoded_x,MODEL_LINEAR_WEIGHTS)
    ly = np.einsum("hwc,c->hw",decoded_y,MODEL_LINEAR_WEIGHTS)
    intended_luma_error = float(np.max(np.abs(
        np.einsum("hwc,c->hw",colored,MODEL_LINEAR_WEIGHTS)-model_luminance)))
    luma_error = float(np.max(np.abs(lx-ly)))
    spread = int(np.max(np.ptp(y.astype(np.int16),axis=2)))
    changed = int(np.count_nonzero(np.any(x != y,axis=2)))
    max_step = max(
        float(np.max(np.abs(np.diff(lx,axis=0)))),
        float(np.max(np.abs(np.diff(lx,axis=1)))),
        float(np.max(np.abs(np.diff(ly,axis=0)))),
        float(np.max(np.abs(np.diff(ly,axis=1)))),
    )
    metrics = {
        "pixel_width":SIZE[0], "pixel_height":SIZE[1],
        "max_intended_linear_luminance_mismatch":intended_luma_error,
        "max_quantized_srgb_proxy_luminance_mismatch":luma_error,
        "max_colored_srgb_channel_spread_8bit":spread,
        "pixels_with_any_condition_difference":changed,
        "max_neighbour_linear_luminance_step":max_step,
        "min_srgb_code":min(int(x.min()),int(y.min())),
        "max_srgb_code":max(int(x.max()),int(y.max())),
    }
    if (intended_luma_error > 1e-12
            or luma_error > MAX_PROXY_LUMINANCE_MISMATCH
            or spread > MAX_SRGB_CHANNEL_SPREAD
            or changed < MIN_CHANGED_PIXELS
            or max_step > MAX_LINEAR_PIXEL_STEP
            or metrics["min_srgb_code"] < 100
            or metrics["max_srgb_code"] > 220):
        raise AssertionError(f"R11 numerical preflight violation: {metrics}")
    return x, y, metrics


def export(out: Path) -> dict:
    """Produces static PNGs and an audit manifest, never human stimuli approval."""
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("refuse to overwrite existing candidate image review directory")
    out.mkdir(parents=True,exist_ok=True)
    stim_dir = out/"candidates_not_approved"
    stim_dir.mkdir()
    records=[]
    for index, word in enumerate(SCENES,1):
        x,y,stats = generate_pair(word)
        files={}
        for code,arr in (("X",x),("Y",y)):
            path=stim_dir/f"{index:02d}_{word}_{code}.png"
            Image.fromarray(arr).save(path,format="PNG",optimize=False)
            files[code]={
                "file":str(path.relative_to(out)),
                "sha256":sha256(path.read_bytes()).hexdigest(),
                "bytes":path.stat().st_size,
            }
        records.append({
            "scene_index":index,"word_label":word,"files":files,
            "numeric_preflight":stats,"operator_reviewed":False,
            "approved_for_participant_display":False,
        })
    with (out/"operator_pairs.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=("pair_index","scene_word",
                                           "condition_X_file","condition_Y_file"))
        writer.writeheader()
        for r in records:
            writer.writerow({
                "pair_index":r["scene_index"],"scene_word":r["word_label"],
                "condition_X_file":r["files"]["X"]["file"],
                "condition_Y_file":r["files"]["Y"]["file"],
            })
    manifest={
        "study":STUDY,"created_by":"deterministic_offline_Pillow_numpy_generator",
        "pillow_version":PIL_VERSION,"numpy_version":np.__version__,
        "condition_X":"grayscale large-word static image",
        "condition_Y":"same scene with weak synthetic chromatic edge component",
        "model_assumptions":{
            "linear_rgb_coefficients":list(float(v) for v in MODEL_LINEAR_WEIGHTS),
            "srgb_transfer":"IEC approximate assumed, not calibrated actual monitor",
            "model_background_luminance":L_BACKGROUND,
            "model_foreground_luminance":L_FOREGROUND,
            "chromatic_edge_field_strength":CHROMA_STRENGTH,
        },
        "numeric_preflight_limits":{
            "max_proxy_luminance_mismatch":MAX_PROXY_LUMINANCE_MISMATCH,
            "max_srgb_channel_spread_8bit":MAX_SRGB_CHANNEL_SPREAD,
            "max_linear_adjacent_pixel_step":MAX_LINEAR_PIXEL_STEP,
            "min_changed_pixels":MIN_CHANGED_PIXELS,
        },
        "scenes":records,
        "operator_map_sha256":sha256((out/"operator_pairs.csv").read_bytes()).hexdigest(),
        "all_still_images":True,"animated_or_flashing_content":False,
        "human_participant_images_displayed":False,
        "human_accommodation_measured":False,
        "experimental_chromablur_efficacy_claim":False,
        "review_state":"AUTOMATED_NUMERIC_PREFLIGHT_ONLY__MANUAL_SAFETY_AND_ETHICS_PENDING",
        "human_exposure_authorized":False,
        "not_a_physical_photometric_calibration":True,
        "limitations":[
            "Automated contrast/color limits are project heuristics, not medically validated safety thresholds",
            "Still images can be uncomfortable; no script can certify all individual seizure/visual risks",
            "Approximate linear luminance matching is not isoluminance on an unmeasured display",
            "The colored image differs from control by slight chroma only; any observed effect is a perceptual confound",
            "Repeated word labels in R10 within-person pairs may bias reading/recognition through practice",
            "Participant study requires separate review, consent, and explicit approval before showing images",
        ],
    }
    (out/"audit_manifest.json").write_text(
        json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+"\n",
        encoding="utf-8")
    return manifest


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",required=True,type=Path)
    args=parser.parse_args()
    m=export(args.out)
    print(json.dumps({
        "study":STUDY,
        "scene_pairs":len(m["scenes"]),
        "still_pngs":sum(len(x["files"]) for x in m["scenes"]),
        "review_state":m["review_state"],
        "human_exposure_authorized":m["human_exposure_authorized"],
    },sort_keys=True))


if __name__=="__main__":
    main()
