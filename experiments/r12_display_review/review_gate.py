#!/usr/bin/env python3
"""R12 manual-review *documentation gate*; never authorizes participant display.

Requires verifiable image provenance and operator checks on the real
screen. Even complete notes require separate owner/ethics authorization.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from generate_candidates import STUDY, SCENES

STATES = {"pending", "pass", "fail"}
REVIEW_STATES = {
    "PENDING_REVIEW_NO_HUMAN_EXPOSURE",
    "REJECTED_BY_OPERATOR",
    "ADMINISTRATIVE_REVIEW_COMPLETE__SEPARATE_AUTHORIZATION_REQUIRED",
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def verify_artifact(root: Path, manifest: dict) -> None:
    """Verify exact file hashes and paths, never trust only the self-report."""
    if manifest.get("study") != STUDY or manifest.get("human_exposure_authorized") is not False:
        raise ValueError("wrong study or non-conservative manifest")
    if manifest.get("human_participants_tested") is not False:
        raise ValueError("the candidate manifest cannot claim a human study")
    records=manifest.get("candidate_pairs")
    if not isinstance(records,list) or len(records)!=len(SCENES):
        raise ValueError("exact four candidate scenes required")
    seen=set()
    for word,rec in zip(SCENES,records):
        if rec.get("word") != word or rec.get("human_display_approved") is not False:
            raise ValueError("candidate word or review state does not match")
        files=rec.get("images")
        if not isinstance(files,dict) or set(files)!={"X","Y"}:
            raise ValueError("exact X/Y files required")
        for code,v in files.items():
            rel=Path(v.get("path",""))
            if (rel.is_absolute() or ".." in rel.parts or rel.suffix.lower()!=".png"
                    or len(rel.parts)!=2 or rel.parts[0]!="UNAPPROVED_images"):
                raise ValueError("unapproved images must remain in candidate directory")
            if str(rel) in seen:
                raise ValueError("duplicate candidate path")
            seen.add(str(rel))
            data=(root/rel).read_bytes()
            digest=sha256(data).hexdigest()
            if not isinstance(v.get("sha256"),str) or digest!=v["sha256"]:
                raise ValueError(f"candidate file digest mismatch: {rel}")
            if len(data)!=v.get("bytes"):
                raise ValueError("candidate byte count mismatch")
        checks=rec.get("numeric_check",{})
        if min(checks.get("modeled_core_large_text_contrast_X",0),
               checks.get("modeled_core_large_text_contrast_Y",0))<3:
            raise ValueError("large-letter contrast too weak in model")
    file=root/"operator_index.csv"
    if sha256(file.read_bytes()).hexdigest()!=manifest.get("operator_index_sha256"):
        raise ValueError("operator index provenance mismatch")


def assess(manifest: dict, review: dict, artifact_root: Path) -> dict:
    verify_artifact(artifact_root,manifest)
    if review.get("study") != STUDY:
        raise ValueError("review study identity mismatch")
    root_digest=sha256((artifact_root/"manifest.json").read_bytes()).hexdigest()
    token=review.get("reviewed_manifest_sha256")
    if token is not None and (
        not isinstance(token,str) or HEX64.fullmatch(token) is None or token != root_digest
    ):
        raise ValueError("operator review must pin the exact original manifest")
    real=review.get("real_display",{})
    pairs=review.get("per_pair",{})
    safeguards=review.get("participant_safeguards",{})
    if (not isinstance(real,dict) or not isinstance(pairs,dict)
            or not isinstance(safeguards,dict) or set(pairs)!=set(SCENES)):
        raise ValueError("review checklist incomplete")
    if review.get("human_exposure_requested") is not False:
        raise ValueError("preflight never authorizes or requests human exposure")
    if review.get("public_media_or_participant_data") is not False:
        raise ValueError("cannot publish study participant footage or identity")
    if safeguards.get("camera_off_by_default") is not True:
        raise ValueError("camera must be optional and off by default")
    if safeguards.get("adult_voluntary_participation_only") is not True:
        raise ValueError("R10/R12 restricts planned feasibility to voluntary adults")
    checkpoints = {}
    checkpoints["authentic_manifest_pinned"]=(token==root_digest)
    checkpoints["operator_viewed_actual_monitor"]=(
        real.get("operator_viewed_actual_monitor") is True)
    checkpoints["nonidentifying_display_alias"]=(
        isinstance(real.get("display_alias"),str) and
        2 <= len(real["display_alias"].strip()) <= 80)
    for field in ("brightness_comfortable","stable_ambient_light",
                  "hdr_and_nightlight_not_changed_during_review",
                  "static_only_without_flashing_or_flicker"):
        state=real.get(field)
        if state not in STATES:
            raise ValueError(f"invalid real-display state: {field}")
        checkpoints["display_"+field]=(state=="pass")
    for word in SCENES:
        if not isinstance(pairs[word],dict):
            raise ValueError("per-pair checklist requires a mapping")
        for check in ("legibility","color_comfort","pattern_risk"):
            state=pairs[word].get(check)
            if state not in STATES:
                raise ValueError(f"{word}: invalid review state {check}")
            checkpoints[f"{word}_{check}"]=(state=="pass")
    ethics=safeguards.get("locally_applicable_ethics_determination")
    if ethics not in STATES:
        raise ValueError("ethics applicability review status required")
    checkpoints["ethics_determination_documented"]=(ethics=="pass")
    checkpoints["ethics_reference_present"]=(
        isinstance(safeguards.get("review_reference"),str)
        and bool(safeguards["review_reference"].strip()))
    for k in ("informed_consent_plan_reviewed",
              "immediate_stop_mechanism_reviewed",
              "privacy_and_retention_plan_reviewed",
              "optional_phone_separate_consent_reviewed"):
        if safeguards.get(k) not in (True,False):
            raise ValueError(f"{k}: explicit boolean required")
        checkpoints[k]=safeguards[k] is True
    explicit_fail=(any(
        real.get(k)=="fail" for k in
        ("brightness_comfortable","stable_ambient_light",
         "hdr_and_nightlight_not_changed_during_review",
         "static_only_without_flashing_or_flicker"))
        or any(item.get(k)=="fail" for item in pairs.values()
               for k in ("legibility","color_comfort","pattern_risk"))
        or ethics=="fail")
    state=("REJECTED_BY_OPERATOR" if explicit_fail else
           "ADMINISTRATIVE_REVIEW_COMPLETE__SEPARATE_AUTHORIZATION_REQUIRED"
           if all(checkpoints.values()) else "PENDING_REVIEW_NO_HUMAN_EXPOSURE")
    return {
        "study":STUDY,"review_state":state,
        "source_manifest_sha256":root_digest,
        "pair_count":len(manifest["candidate_pairs"]),
        "checkpoints_completed":sum(checkpoints.values()),
        "checkpoints_total":len(checkpoints),
        "remaining_checks":[k for k,v in checkpoints.items() if not v],
        "human_exposure_authorized":False,
        "phone_recording_authorized":False,
        "human_data_collected":False,
        "measured_accommodation":False,
        "interpretation":"ADMINISTRATIVE_AND_STATIC_IMAGE_AUDIT_ONLY",
    }


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidates",type=Path,required=True)
    p.add_argument("--review",type=Path,required=True)
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    manifest=json.loads((args.candidates/"manifest.json").read_text(encoding="utf-8"))
    review=json.loads(args.review.read_text(encoding="utf-8"))
    result=assess(manifest,review,args.candidates)
    payload=json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False)+"\n"
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(payload,encoding="utf-8")
    print(payload,end="")


if __name__=="__main__":
    main()
