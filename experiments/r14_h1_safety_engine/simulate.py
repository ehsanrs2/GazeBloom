#!/usr/bin/env python3
"""R14 simulation-only CI evidence: no people, images, face video or real timings."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path

from session import SimulatedSession, VIEW_S, REST_S, STUDY

SCENES=("NOVA","LUMA","MIRA","TORA")
SEQ=("X","Y","Y","X","Y","X","X","Y")


def fake_binding() -> list[dict]:
    """P000-style fixture: filename shapes, no real images or real participant."""
    rows=[]
    for i in range(8):
        word=SCENES[i%4]
        arm=SEQ[i]
        rows.append({
            "trial_id":f"T{i+1:02d}", "condition_code":arm, "word":word,
            "image_relative_path":f"UNAPPROVED_images/{i%4+1:02d}_{word}_{arm}.png",
            "image_sha256":sha256(f"FAKE_R14_FIXTURE|{word}|{arm}".encode()).hexdigest(),
            "max_view_seconds":"10","min_rest_seconds":"30",
        })
    return rows


def run_scenarios() -> dict:
    binding=fake_binding()
    full=SimulatedSession(binding)
    t=0.
    for i in range(8):
        full.start(t)
        full.tick(t+VIEW_S)
        full.record_response(t+VIEW_S+.1,clarity=7,comfort=7,reading_correct=True)
        t+=VIEW_S+.1
        if i!=7:
            full.tick(t+REST_S)
            t+=REST_S
    assert full.report()["terminal_state"]=="FINISHED"
    assert full.report()["response_rows"]==8

    active=SimulatedSession(binding)
    active.start(0.)
    active.stop(1.)
    assert active.report()["terminal_state"]=="STOPPED"
    assert active.report()["response_rows"]==1

    rest=SimulatedSession(binding)
    rest.start(0.)
    rest.tick(10.)
    rest.record_response(10.1,clarity=7,comfort=6,reading_correct=True)
    rest.stop(11.)
    assert rest.report()["response_rows"]==1
    assert rest.report()["terminal_state"]=="STOPPED"

    discomfort=SimulatedSession(binding)
    discomfort.start(0.)
    discomfort.tick(10.)
    discomfort.record_response(10.1,discomfort=True)
    assert discomfort.report()["terminal_state"]=="STOPPED"
    assert discomfort.rows[-1]["discomfort_flag"]=="1"

    return {
        "study":STUDY,
        "cases":{
            "normal_eight_trials":full.report(),
            "stop_while_simulated_viewing":active.report(),
            "stop_during_virtual_rest":rest.report(),
            "discomfort_permanent_stop":discomfort.report(),
        },
        "all_cases_complete":True,
        "human_exposure_authorized":False,
        "human_participants":0,
        "camera_recordings":0,
        "actual_pngs_opened":0,
        "private_human_consent_collected":False,
        "actual_display_timing_verified":False,
        "interpretation":"SOFTWARE_SIMULATION_ONLY_NOT_HUMAN_RESEARCH",
    }


def main() -> None:
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():
        raise FileExistsError("refuse to replace prior R14 simulation report")
    report=run_scenarios()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "study":STUDY,
        "cases":list(report["cases"]),
        "mode":report["interpretation"],
        "human_exposure_authorized":False,
    },sort_keys=True))


if __name__=="__main__":
    main()
