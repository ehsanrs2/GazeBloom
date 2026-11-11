#!/usr/bin/env python3
"""R12 high-contrast still candidate/control pairs; NOT human-study authorization.

R11's model luminances yielded ~1.40:1 contrast for letters. R12
addresses readability as a potential confound by using a >=3:1
large-letter reference contrast in an *uncalibrated sRGB model*.
This is not a device measurement, seizure-risk certification, or
a direct measure of accommodation.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageFilter, __version__ as PIL_VERSION

EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP/"r11_static_stimuli"))
from generate import (  # noqa: E402
    SIZE, SCENES, MODEL_LINEAR_WEIGHTS as WEIGHTS, label_mask,
    linear_to_srgb, srgb_to_linear,
)

STUDY = "GAZEBLOOM_R12_STATIC_CONTRAST_SAFETY_PREVIEW_V1"
BACKGROUND_LINEAR = .56
TEXT_LINEAR = .14
CHROMA_STRENGTH = .036
REFERENCE_LARGE_TEXT_CONTRAST = 3.0  # WCAG-inspired *model check only*
MAX_MODEL_LUMINANCE_MISMATCH = .008
MAX_RGB_CHANNEL_SPREAD_CODE = 11
MAX_ADJACENT_MODEL_LUMINANCE_STEP = .22
MIN_CHANGED_PIXELS = 2500


def contrast_ratio(foreground: float, background: float) -> float:
    if not (0 <= foreground <= 1 and 0 <= background <= 1):
        raise ValueError("linear luminances must be in [0,1]")
    bright, dark = sorted((foreground, background), reverse=True)
    return (bright + .05)/(dark + .05)


def generate_pair(word: str) -> tuple[np.ndarray, np.ndarray, dict]:
    """Build two 640x360 RGB PNG arrays with equal assumed linear luminance."""
    mask = label_mask(word)
    region = np.asarray(mask, dtype=np.float64)/255.
    base = BACKGROUND_LINEAR + (TEXT_LINEAR-BACKGROUND_LINEAR)*region
    near = np.asarray(mask.filter(ImageFilter.GaussianBlur(2)),
                      dtype=np.float64)/255.
    wide = np.asarray(mask.filter(ImageFilter.GaussianBlur(9)),
                      dtype=np.float64)/255.
    color = CHROMA_STRENGTH*(near-wide)
    x_linear = np.repeat(base[...,None],3,axis=-1)
    y_linear = np.stack((
        base+color,
        base-color*float(WEIGHTS[0]/WEIGHTS[1]),
        base,
    ),axis=-1)
    if (x_linear.min()<0 or x_linear.max()>1
            or y_linear.min()<0 or y_linear.max()>1):
        raise ValueError("proposed design out of RGB gamut")
    pre_error = float(np.max(np.abs(
        np.einsum("hwc,c->hw",y_linear,WEIGHTS)-base)))
    x = np.rint(linear_to_srgb(x_linear)*255).astype(np.uint8)
    y = np.rint(linear_to_srgb(y_linear)*255).astype(np.uint8)
    x_decode = srgb_to_linear(x.astype(float)/255)
    y_decode = srgb_to_linear(y.astype(float)/255)
    lum_x = np.einsum("hwc,c->hw",x_decode,WEIGHTS)
    lum_y = np.einsum("hwc,c->hw",y_decode,WEIGHTS)
    flat_text = region > .99
    flat_back = region < .001
    if flat_text.sum()<500 or flat_back.sum()<500:
        raise ValueError("too few core text/background pixels")
    ratio_x = contrast_ratio(float(np.median(lum_x[flat_text])),
                             float(np.median(lum_x[flat_back])))
    ratio_y = contrast_ratio(float(np.median(lum_y[flat_text])),
                             float(np.median(lum_y[flat_back])))
    mismatch = float(np.max(np.abs(lum_x-lum_y)))
    spread = int(np.max(np.ptp(y.astype(np.int16),axis=2)))
    changed = int(np.count_nonzero(np.any(x!=y,axis=2)))
    max_step = max(float(np.max(np.abs(np.diff(lum,axis=axis))))
                   for lum in (lum_x,lum_y) for axis in (0,1))
    metrics = {
        "word":word,
        "modeled_core_large_text_contrast_X":ratio_x,
        "modeled_core_large_text_contrast_Y":ratio_y,
        "model_prequantized_luminance_mismatch":pre_error,
        "model_postquantized_luminance_mismatch":mismatch,
        "max_8bit_rgb_channel_spread_Y":spread,
        "changed_pixels_X_vs_Y":changed,
        "max_neighbor_linear_luminance_step":max_step,
        "min_rgb_code":min(int(x.min()),int(y.min())),
        "max_rgb_code":max(int(x.max()),int(y.max())),
    }
    if (min(ratio_x,ratio_y) < REFERENCE_LARGE_TEXT_CONTRAST
        or pre_error > 1e-12
        or mismatch > MAX_MODEL_LUMINANCE_MISMATCH
        or spread > MAX_RGB_CHANNEL_SPREAD_CODE
        or changed < MIN_CHANGED_PIXELS
        or max_step > MAX_ADJACENT_MODEL_LUMINANCE_STEP
        or metrics["min_rgb_code"] < 95
        or metrics["max_rgb_code"] > 210):
        raise AssertionError(f"R12 static-preview numeric rejection: {metrics}")
    return x,y,metrics


def export(out: Path) -> dict:
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("never overwrite existing stimulus candidates")
    out.mkdir(parents=True,exist_ok=True)
    images=out/"UNAPPROVED_images"
    images.mkdir()
    records=[]
    for k,word in enumerate(SCENES,1):
        x,y,metrics=generate_pair(word)
        names={}
        for c,pixels in (("X",x),("Y",y)):
            path=images/f"{k:02d}_{word}_{c}.png"
            Image.fromarray(pixels).save(path,format="PNG",optimize=False)
            names[c]={"path":str(path.relative_to(out)),
                      "sha256":sha256(path.read_bytes()).hexdigest(),
                      "bytes":path.stat().st_size}
        records.append({
            "pair_index":k,"word":word,"images":names,
            "numeric_check":metrics,
            "operator_display_review":"PENDING",
            "human_display_approved":False,
        })
    with (out/"operator_index.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=("pair_index","word","X_path","Y_path"))
        writer.writeheader()
        for rec in records:
            writer.writerow({
                "pair_index":rec["pair_index"],"word":rec["word"],
                "X_path":rec["images"]["X"]["path"],
                "Y_path":rec["images"]["Y"]["path"],
            })
    manifest={
        "study":STUDY,
        "original_R11_reference_contrast":contrast_ratio(.37,.54),
        "r12_design_reference_contrast":contrast_ratio(TEXT_LINEAR,BACKGROUND_LINEAR),
        "model_contrast_reference":"WCAG_3_TO_1_LARGE_TEXT_INSPIRED_NOT_DEVICE_CERTIFICATION",
        "all_images_static":True,
        "real_display_luminance_measured":False,
        "individual_photic_safety_certified":False,
        "review":"SOFTWARE_NUMERIC_ONLY__REAL_DISPLAY_ETHICS_CONSENT_REVIEW_PENDING",
        "human_participants_tested":False,
        "human_exposure_authorized":False,
        "camera_required":False,
        "candidate_pairs":records,
        "versions":{"numpy":np.__version__,"Pillow":PIL_VERSION},
        "operator_index_sha256":sha256((out/"operator_index.csv").read_bytes()).hexdigest(),
        "limitations":[
            "WCAG contrast is an accessibility reference not a human-study safety threshold",
            "Same Rec709 assumed linear luminance does not imply physical isoluminance",
            "Flat large letters still need operator review for comfort and phosensitivity",
            "Word repetition may affect reading; same words under X/Y are not independent",
            "No dynamic presentation, consent, camera, participant data or efficacy claims",
        ],
    }
    (out/"manifest.json").write_text(
        json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",
        encoding="utf-8")
    return manifest


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    m=export(args.out)
    print(json.dumps({
        "study":STUDY,
        "pairs":len(m["candidate_pairs"]),
        "review":m["review"],
        "human_exposure_authorized":m["human_exposure_authorized"],
    },sort_keys=True))


if __name__=="__main__":
    main()
