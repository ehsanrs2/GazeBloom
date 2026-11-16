#!/usr/bin/env python3
"""R15 read-only governance status report: never authorizes human exposure.

Reads the local R12 assessment and separate human-entered governance
template. Validates forms and records unresolved gaps. Does NOT verify
ethics authority, legal sufficiency, signatures, consent, or human-runner
safety. Even complete administrative paperwork cannot authorize H1.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re

STUDY = "GAZEBLOOM_R15_H1_GOVERNANCE_READINESS_V1"
R12_STUDY = "GAZEBLOOM_R12_STATIC_CONTRAST_SAFETY_PREVIEW_V1"
R12_SHA = "1b533d4dcf9c7225749529a79f2e6bda8d497d3807398270f8059d869e9fefdf"
R12_PENDING = {
    "ethics_reference_present", "informed_consent_plan_reviewed",
    "immediate_stop_mechanism_reviewed", "privacy_and_retention_plan_reviewed",
    "optional_phone_separate_consent_reviewed",
}
STATUS = {"pending", "reviewed", "rejected"}
SHA = re.compile(r"^[0-9a-f]{64}$")
CONTEXT = {"independent", "university", "institution"}


def _meaningful(value: object) -> bool:
    return (isinstance(value, str) and 2 <= len(value.strip()) <= 160
            and value.strip().lower() not in
            {"tbd", "pending", "unknown", "none", "na", "n/a", "test", "todo"})


def _status(obj: object, key: str) -> str:
    if not isinstance(obj, dict):
        raise ValueError(f"{key}: expected object")
    state = obj.get("review_status")
    if state not in STATUS:
        raise ValueError(f"{key}: expected pending/reviewed/rejected")
    return state


def audit(r12: dict, form: dict) -> dict:
    if r12.get("study") != R12_STUDY:
        raise ValueError("R12 report study mismatch")
    if r12.get("source_manifest_sha256") != R12_SHA:
        raise ValueError("R12 original candidate-image SHA-256 mismatch")
    if (r12.get("human_exposure_authorized") is not False
            or r12.get("phone_recording_authorized") is not False
            or r12.get("human_data_collected") is not False):
        raise ValueError("expected R12 report without human exposure, phone or data")
    completed, total = r12.get("checkpoints_completed"), r12.get("checkpoints_total")
    if (not isinstance(completed,int) or isinstance(completed,bool)
            or not isinstance(total,int) or isinstance(total,bool)
            or total!=25 or not 0<=completed<=total):
        raise ValueError("invalid R12 checklist counts")
    remaining=r12.get("remaining_checks")
    if (not isinstance(remaining,list) or len(remaining)!=total-completed
            or not all(isinstance(x,str) and x for x in remaining)
            or len(set(remaining))!=len(remaining)):
        raise ValueError("incoherent R12 pending-check inventory")
    if form.get("study")!=STUDY:
        raise ValueError("R15 input study mismatch")
    if form.get("human_exposure_requested") is not False:
        raise ValueError("R15 cannot request or authorize human exposure")
    op=form.get("operator_r14_demo")
    if (not isinstance(op,dict) or op.get("reported_functional") is not True
            or op.get("scope")!="OPERATOR_ONLY_NEUTRAL_PLACEHOLDERS"
            or op.get("real_human_stimuli_displayed") is not False
            or op.get("measured_stop_latency_ms") is not None):
        raise ValueError("R14 subjective operator-demo result is only narrow evidence")
    locality=form.get("jurisdiction")
    if not isinstance(locality,dict):
        raise ValueError("jurisdiction must be object")
    context=locality.get("study_context")
    if context is not None and context not in CONTEXT:
        raise ValueError("study_context requires independent/university/institution")
    country=locality.get("country")
    if country is not None and not _meaningful(country):
        raise ValueError("country must be a meaningful name when supplied")
    camera=form.get("optional_camera")
    if not isinstance(camera,dict) or camera.get("camera_off_by_default") is not True:
        raise ValueError("camera must be off by default")
    group_names=("ethics","consent","privacy","human_stop","optional_camera")
    status={key:_status(form.get(key),key) for key in group_names}
    reasons=[]
    if country is None or context is None:
        reasons.append("study_country_and_institutional_context_UNSPECIFIED")
    ethics=form["ethics"]
    if status["ethics"] == "reviewed":
        if not (country is not None and context is not None
                and _meaningful(ethics.get("competent_authority_reference"))
                and _meaningful(ethics.get("decision_reference"))):
            reasons.append("ethics_review_reference_OR_jurisdiction_MISSING")
        if not isinstance(ethics.get("formal_approval_if_required"),bool):
            raise ValueError("ethics approval applicability flag must be explicit bool")
    else:
        reasons.append("real_ethics_determination_PENDING")
    consent=form["consent"]
    if status["consent"]=="reviewed":
        hash_value=consent.get("final_document_sha256")
        if (not isinstance(hash_value,str) or SHA.fullmatch(hash_value) is None
                or not _meaningful(consent.get("review_reference"))):
            reasons.append("final_consent_review_evidence_MISSING")
    else:
        reasons.append("informed_consent_FINAL_REVIEW_PENDING")
    privacy=form["privacy"]
    if status["privacy"]=="reviewed":
        retention=privacy.get("retention_days")
        if (not _meaningful(privacy.get("data_controller_reference"))
                or not isinstance(retention,int) or isinstance(retention,bool)
                or not 0<retention<=3650
                or not _meaningful(privacy.get("deletion_policy_reference"))):
            reasons.append("data_controller_retention_deletion_review_MISSING")
    else:
        reasons.append("data_protection_FINAL_REVIEW_PENDING")
    stop=form["human_stop"]
    if (status["human_stop"]!="reviewed"
            or not _meaningful(stop.get("real_participant_runner_test_report"))):
        reasons.append("actual_H1_runner_and_stop_validation_NOT_PRESENT")
    if (status["optional_camera"]!="reviewed"
            or not _meaningful(camera.get("separate_consent_policy_reference"))):
        reasons.append("phone_separate_consent_review_PENDING__PHONE_REMAINS_OFF")
    if any(v=="rejected" for v in status.values()):
        reasons.append("at_least_one_governance_gate_REJECTED")
    if remaining:
        reasons.append("R12_original_five_checklist_items_UNRESOLVED")
    # This module cannot validate signatures, provenance or competent authority.
    # Human-participant software is not implemented or approved in R14/R15.
    reasons.append("independent_human_participant_runner_authorization_NOT_IMPLEMENTED")
    return {
        "study":STUDY,
        "operator_r14_demo":"FUNCTION_REPORTED_PASS__NO_LATENCY_MEASUREMENT",
        "r12_candidate_manifest_sha256":R12_SHA,
        "r12_checkpoints":f"{completed}/{total}",
        "r12_unresolved":remaining,
        "governance_review_states":status,
        "unresolved_reasons":reasons,
        "decision":"H1_NOT_AUTHORIZED__GOVERNANCE_AND_REAL_RUNNER_PENDING",
        "human_exposure_authorized":False,
        "phone_recording_authorized":False,
        "human_study_data_collected":False,
        "measured_accommodation":False,
        "evidence_scope":"LOCAL_OPERATOR_REPORT_PLUS_SOFTWARE_DOCUMENTS",
    }


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r12-report",type=Path,required=True)
    parser.add_argument("--form",type=Path,required=True)
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    result=audit(
        json.loads(args.r12_report.read_text(encoding="utf-8")),
        json.loads(args.form.read_text(encoding="utf-8")),
    )
    payload=json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        # An exclusive create rejects both an existing file and a symlink;
        # private local governance outputs must not inherit a world-readable umask.
        try:
            fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise FileExistsError("refuse overwrite of prior private governance status") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
    print(payload,end="")


if __name__=="__main__":
    main()
