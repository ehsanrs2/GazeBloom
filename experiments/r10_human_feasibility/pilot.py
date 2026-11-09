#!/usr/bin/env python3
"""R10 offline perceptual pilot scaffolding: no exposure, camera or biometric I/O.

A schedule is NOT consent, ethics clearance, eye accommodation measurement,
safety certification or permission to display research stimuli to humans.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import re

STUDY = "GAZEBLOOM_R10_PERCEPTION_PHONE_OPTIONAL_V1"
PLAN_FIELDS = ("trial_id", "condition_code", "max_view_seconds",
               "min_rest_seconds")
RESPONSE_FIELDS = ("trial_id", "clarity_0_10", "comfort_0_10",
                   "reading_correct", "discomfort_flag", "stopped")
CAMERA_FIELDS = ("time_s", "face_visible", "lighting_stable",
                 "blink_event", "pupil_px", "iris_px")
DURATION_S = 10
REST_S = 30
SEQ = ("X", "Y", "Y", "X", "Y", "X", "X", "Y")
PARTICIPANT_CODE = re.compile(r"^P[0-9]{3,6}$")


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path, fields: tuple[str, ...]) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != list(fields):
            raise ValueError(f"{path.name}: expected exactly {','.join(fields)}")
        rows = list(reader)
        if any(None in row for row in rows):
            raise ValueError("extra unlabeled CSV fields are not allowed")
        return rows


def make_plan(code: str, seed: str) -> tuple[list[dict], dict]:
    """Balanced X/Y sequence, varied deterministically across pseudonyms."""
    if PARTICIPANT_CODE.fullmatch(code) is None:
        raise ValueError("participant code must be a pseudonym such as P001")
    if not isinstance(seed, str) or len(seed) < 8:
        raise ValueError("study seed must have >=8 characters; store it privately")
    bit = sha256((seed + "|" + code).encode()).digest()[0] & 1
    sequence = [("Y" if x=="X" else "X") if bit else x for x in SEQ]
    rows = [{"trial_id": f"T{i:02d}", "condition_code":condition,
             "max_view_seconds":str(DURATION_S),
             "min_rest_seconds":str(REST_S)}
            for i,condition in enumerate(sequence, start=1)]
    manifest = {
        "study":STUDY,"participant_code":code,"n_planned_trials":len(rows),
        "condition_labels":{"X":"operator-reviewed control",
                            "Y":"operator-reviewed test"},
        "count_per_condition":{"X":sequence.count("X"),
                               "Y":sequence.count("Y")},
        "max_view_seconds":DURATION_S,"min_rest_seconds":REST_S,
        "camera_required":False,"research_stimuli_included":False,
        "human_test_authorized_by_script":False,
        "outcome_scope":"PERCEPTUAL_REPORT_ONLY_NO_EYE_ACCOMMODATION",
        "blinding_limit":"participant may visually recognize color differences",
    }
    return rows, manifest


def _as_bool(value: str, *, allow_empty: bool = False) -> bool | None:
    if allow_empty and value == "":
        return None
    if value not in ("0", "1"):
        raise ValueError("Boolean fields must be 0 or 1")
    return value == "1"


def _as_score(value: str) -> float | None:
    if value == "":
        return None
    try:
        score=float(value)
    except (ValueError, TypeError) as e:
        raise ValueError("rating must be a number 0..10") from e
    if not 0 <= score <= 10 or score != score:
        raise ValueError("rating must be finite 0..10")
    return score


def analyze_responses(plan: list[dict], responses: list[dict]) -> dict:
    if len(plan)!=8 or len({r["trial_id"] for r in plan})!=8:
        raise ValueError("R10 plan requires eight unique trials")
    by_id = {x["trial_id"]:x for x in plan}
    if set(x["condition_code"] for x in plan)!={"X","Y"}:
        raise ValueError("plan must contain both conditions")
    observed=set()
    counts={"X":{"n":0,"clarity":[],"comfort":[],"reading_correct":[]},
            "Y":{"n":0,"clarity":[],"comfort":[],"reading_correct":[]}}
    stopped_count=0
    discomfort_count=0
    for row in responses:
        trial=row["trial_id"]
        if trial not in by_id or trial in observed:
            raise ValueError(f"unknown or duplicated trial id {trial!r}")
        observed.add(trial)
        stopped=_as_bool(row["stopped"])
        discomfort=_as_bool(row["discomfort_flag"])
        # A request to stop is not missingness to erase; it is an outcome.
        if discomfort:
            discomfort_count+=1
        if stopped:
            stopped_count+=1
            continue
        clarity=_as_score(row["clarity_0_10"])
        comfort=_as_score(row["comfort_0_10"])
        if clarity is None or comfort is None:
            raise ValueError("completed trials require clarity and comfort ratings")
        correct=_as_bool(row["reading_correct"], allow_empty=True)
        arm=by_id[trial]["condition_code"]
        counts[arm]["n"]+=1
        counts[arm]["clarity"].append(clarity)
        counts[arm]["comfort"].append(comfort)
        if correct is not None:
            counts[arm]["reading_correct"].append(int(correct))
    def mean(values: list[float]) -> float | None:
        return sum(values)/len(values) if values else None
    return {
        "study":STUDY,
        "evidence_state":"ACTUAL_RESPONSES_IF_GENUINELY_COLLECTED__SELF_REPORT_NOT_ACCOMMODATION",
        "planned_trials":len(plan),"rows_submitted":len(responses),
        "not_submitted_trials":len(plan)-len(responses),
        "stopped_trials":stopped_count,"discomfort_flags":discomfort_count,
        "condition_summary":{arm:{
            "completed_n":x["n"],
            "mean_clarity_0_10":mean(x["clarity"]),
            "mean_comfort_0_10":mean(x["comfort"]),
            "reading_correct_fraction":mean(x["reading_correct"]),
        } for arm,x in counts.items()},
        "exploratory_only":True,"inferential_p_value":None,
        "human_accommodation_diopters":None,
        "clinical_efficacy_or_diagnosis":None,
        "interpretation_warning":
            "Optional self-report; fatigue, brightness, expectations, color, task and order can confound. "
            "No measured diopters, neural accommodation or therapeutic inference.",
    }


def analyze_camera_annotations(rows: list[dict]) -> dict:
    """Manual frame-level annotations. Does NOT open or infer from face video."""
    last=None
    good_duration=0.
    blinks=0
    ratios=[]
    quality_frames=0
    prev_good=False
    for row in rows:
        t=float(row["time_s"])
        if not isfinite(t) or not 0 <= t < 86400 or (last is not None and t<=last):
            raise ValueError("timestamps must be finite, strictly increasing and >=0")
        face=_as_bool(row["face_visible"])
        light=_as_bool(row["lighting_stable"])
        blink=_as_bool(row["blink_event"])
        good=face and light
        if blink and not good:
            raise ValueError("blink annotation requires face visibility and stable lighting")
        if good:
            quality_frames+=1
        if good and prev_good and last is not None and t-last<=.5:
            good_duration+=t-last
            if blink:
                blinks+=1
        if row["pupil_px"]!="" or row["iris_px"]!="":
            if not good or not row["pupil_px"] or not row["iris_px"]:
                raise ValueError("pupil-to-iris annotation requires good frame and both radii")
            pup=float(row["pupil_px"])
            iris=float(row["iris_px"])
            if not isfinite(pup) or not isfinite(iris) or not 0<pup<iris or iris<2:
                raise ValueError("radii must be positive, bounded and pupil < iris")
            ratios.append(pup/iris)
        last=t
        prev_good=good
    blink_rate = blinks*60/good_duration if good_duration>=5 else None
    return {
        "study":STUDY,"source":"MANUAL_OPT_IN_CSV_ANNOTATIONS_ONLY",
        "frames_annotated":len(rows),"quality_frames":quality_frames,
        "approx_valid_video_seconds":round(good_duration,4),
        "blink_events_in_valid_contiguous_segments":blinks,
        "blink_per_valid_minute_proxy":blink_rate,
        "pupil_iris_ratio_mean_proxy":sum(ratios)/len(ratios) if ratios else None,
        "pupil_measurements_used":len(ratios),
        "quality_note":"valid duration requires adjacent good annotated frames <=0.5 sec apart; "
                       "event counts are annotation-dependent",
        "absolute_pupil_mm":None,"accommodation_diopters":None,
        "photo_or_video_captured_by_script":False,
        "biometric_identity_inferred":False,
        "medical_interpretation_allowed":False,
    }


def main() -> None:
    # Session plans and any actual participant annotations stay local/private.
    # Restrictive file permissions protect files created by this CLI.
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest="command",required=True)
    plan=commands.add_parser("plan")
    plan.add_argument("--participant-code",required=True)
    plan.add_argument("--seed",required=True)
    plan.add_argument("--out",type=Path,required=True)
    ana=commands.add_parser("analyze")
    ana.add_argument("--plan",type=Path,required=True)
    ana.add_argument("--responses",type=Path,required=True)
    ana.add_argument("--out",type=Path,required=True)
    cam=commands.add_parser("camera")
    cam.add_argument("--annotations",type=Path,required=True)
    cam.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    if args.command=="plan":
        if args.out.exists() and any(args.out.iterdir()):
            raise ValueError("plan directory must be empty to avoid overwriting private data")
        data,manifest=make_plan(args.participant_code,args.seed)
        _write_csv(args.out/"trials.csv",PLAN_FIELDS,data)
        _write_csv(args.out/"responses_TEMPLATE.csv",RESPONSE_FIELDS,
                   [{"trial_id":x["trial_id"]} for x in data])
        (args.out/"manifest.json").write_text(
            json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        result=manifest
    elif args.command=="analyze":
        result=analyze_responses(_read_csv(args.plan,PLAN_FIELDS),
                                 _read_csv(args.responses,RESPONSE_FIELDS))
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    else:
        result=analyze_camera_annotations(_read_csv(args.annotations,CAMERA_FIELDS))
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))


if __name__=="__main__":
    main()
