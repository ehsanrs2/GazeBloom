#!/usr/bin/env python3
"""R13 local H0-only operator setup for the R12 static candidate images.

This script is NOT a participant player or a human-study approval. It
does not open cameras, record responses, schedule timed stimulus display,
collect identifying information, or infer ocular accommodation.

"inspect" deliberately opens static images on the operator's *actual*
monitor (only after explicit command-line acknowledgement). No participant
should be present, and no safe-for-humans conclusion follows.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
import os
from pathlib import Path
import random
import re
import sys

HERE = Path(__file__).resolve().parent
EXPERIMENTS = HERE.parent
sys.path.insert(0, str(EXPERIMENTS / "r12_display_review"))
sys.path.insert(0, str(EXPERIMENTS / "r10_human_feasibility"))

from generate_candidates import SCENES, STUDY as R12_STUDY  # noqa: E402
from review_gate import verify_artifact, assess  # noqa: E402
from pilot import PLAN_FIELDS, _read_csv  # noqa: E402

STUDY = "GAZEBLOOM_R13_LOCAL_OPERATOR_REVIEW_V1"
BINDING_FIELDS = (
    "trial_id", "condition_code", "word", "image_relative_path",
    "image_sha256", "max_view_seconds", "min_rest_seconds",
)
CONDITION_SEQUENCE = ("X", "Y", "Y", "X", "Y", "X", "X", "Y")
_ID = re.compile(r"^P[0-9]{3,6}$")


def _private_dir_empty(path: Path) -> None:
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise FileExistsError("destination must be absent or an empty directory")
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False,
                               sort_keys=True) + "\n", encoding="utf-8")


def open_candidate_set(root: Path) -> tuple[dict, str]:
    raw = (root / "manifest.json").read_bytes()
    manifest = json.loads(raw)
    verify_artifact(root, manifest)
    digest = sha256(raw).hexdigest()
    if manifest["study"] != R12_STUDY or manifest.get("human_exposure_authorized") is not False:
        raise ValueError("R12 unapproved candidates only")
    return manifest, digest


def prepare_review(root: Path, out: Path) -> dict:
    """Seed a PRIVATE, pinned, entirely PENDING review; do not fake operator PASS."""
    manifest, digest = open_candidate_set(root)
    template = json.loads(
        (EXPERIMENTS / "r12_display_review" / "review_template.json")
        .read_text(encoding="utf-8"))
    template["reviewed_manifest_sha256"] = digest
    # Verify that pinning alone does not authorize anything.
    report = assess(manifest, template, root)
    assert not report["human_exposure_authorized"]
    assert report["review_state"] == "PENDING_REVIEW_NO_HUMAN_EXPOSURE"
    _private_dir_empty(out)
    _write_json(out / "review_PENDING.json", template)
    _write_json(out / "review_status_PENDING.json", report)
    _write_json(out / "operator_instructions.json", {
        "study": STUDY,
        "source_manifest_sha256": digest,
        "purpose": "H0_LOCAL_OPERATOR_ONLY__NO_PARTICIPANT_EXPOSURE",
        "instructions": [
            "Inspect only on the intended monitor with no research participant present",
            "Write observations in a LOCAL copy of review_PENDING.json, not the public repository",
            "Review luminance/ICC/HDR/Night Light, word readability, halo patterns, stop controls",
            "Complete actual local ethics determination, consent and optional camera consent separately",
            "Validate local notes with R12 review_gate.py; even all PASS never grants exposure authorization",
            "Do not upload real participant/face/consent/device identifiers into public GitHub",
        ],
        "human_exposure_authorized": False,
        "phone_camera_required": False,
        "automatic_stimulus_presentation": False,
        "human_accommodation_measured": False,
    })
    return report


def _validate_plan(plan: list[dict], plan_manifest: dict) -> None:
    if len(plan) != 8 or plan_manifest.get("n_planned_trials") != 8:
        raise ValueError("exact eight R10 plan trials required")
    if plan_manifest.get("human_test_authorized_by_script") is not False:
        raise ValueError("only non-authorizing R10 plans are allowed")
    if plan_manifest.get("camera_required") is not False:
        raise ValueError("camera must be OFF by default")
    if plan_manifest.get("research_stimuli_included") is not False:
        raise ValueError("unreviewed stimulus-presenting plans cannot be rebound")
    if not _ID.fullmatch(str(plan_manifest.get("participant_code", ""))):
        raise ValueError("pseudonymous participant code required")
    for i, row in enumerate(plan):
        if row["trial_id"] != f"T{i+1:02d}":
            raise ValueError("trial IDs must be T01..T08")
        if row["condition_code"] not in ("X", "Y"):
            raise ValueError("condition code must be X or Y")
        if row["max_view_seconds"] != "10" or row["min_rest_seconds"] != "30":
            raise ValueError("R10 frozen viewing/rest limits must be preserved")
    conditions = [x["condition_code"] for x in plan]
    if conditions not in (list(CONDITION_SEQUENCE),
                          ["Y" if x == "X" else "X" for x in CONDITION_SEQUENCE]):
        raise ValueError("unexpected R10 counterbalancing order")
    if any(conditions[i] == conditions[i+4] for i in range(4)):
        raise ValueError("each word requires opposite conditions four trials apart")


def bind_pairs(root: Path, plan: list[dict], plan_manifest: dict,
               binding_seed: str) -> tuple[list[dict], dict]:
    """Each of four words occurs once X and once Y, exactly 4 trials apart.

    Word order is deterministic from a private study seed and a
    pseudonymous participant code. No participant images are displayed.
    """
    original, original_sha = open_candidate_set(root)
    _validate_plan(plan, plan_manifest)
    if not isinstance(binding_seed, str) or len(binding_seed) < 12:
        raise ValueError("local binding seed needs at least 12 characters")
    # Seed itself is never recorded in public artifacts.
    digest = sha256(
        (binding_seed + "|R13|" + plan_manifest["participant_code"]
         + "|" + original_sha).encode("utf-8")
    ).digest()
    words = list(SCENES)
    random.Random(int.from_bytes(digest, "big")).shuffle(words)
    source = {p["word"]: p for p in original["candidate_pairs"]}
    rows = []
    for i, trial in enumerate(plan):
        word = words[i % 4]
        img = source[word]["images"][trial["condition_code"]]
        rows.append({
            "trial_id": trial["trial_id"],
            "condition_code": trial["condition_code"],
            "word": word,
            "image_relative_path": img["path"],
            "image_sha256": img["sha256"],
            "max_view_seconds": trial["max_view_seconds"],
            "min_rest_seconds": trial["min_rest_seconds"],
        })
    verify_pair_balance(rows)
    result = {
        "study": STUDY,
        "candidate_manifest_sha256": original_sha,
        "r10_plan_study": plan_manifest.get("study"),
        "participant_code": plan_manifest["participant_code"],
        "planned_trial_count": len(rows),
        "word_count": len(words),
        "each_word_once_per_condition": True,
        "repeat_separation_trials": 4,
        "camera_required": False,
        "human_exposure_authorized": False,
        "participant_responses_present": False,
        "medical_or_accommodation_inference": False,
        "display_approval_source": "NONE__PRIVATE_OPERATOR_REVIEW_AND_SEPARATE_AUTHORIZATION_REQUIRED",
        "limitation": "Repeated word can cause recall/learning; visibility of color limits blinding",
    }
    return rows, result


def verify_pair_balance(rows: list[dict]) -> None:
    if len(rows) != 8:
        raise ValueError("exact 8 rows required")
    for i in range(4):
        a,b = rows[i], rows[i+4]
        if a["word"] != b["word"] or a["condition_code"] == b["condition_code"]:
            raise ValueError("each word must repeat at lag four in opposite arm")
    for word in SCENES:
        vals = [r["condition_code"] for r in rows if r["word"] == word]
        if sorted(vals) != ["X", "Y"]:
            raise ValueError("each scene must have exactly one X and one Y")
    if len({r["trial_id"] for r in rows}) != len(rows):
        raise ValueError("trial identifiers must be unique")


def write_binding(root: Path, plan_file: Path, plan_manifest_file: Path,
                  seed: str, output: Path) -> dict:
    plan = _read_csv(plan_file, PLAN_FIELDS)
    plan_manifest = json.loads(plan_manifest_file.read_text(encoding="utf-8"))
    rows, summary = bind_pairs(root, plan, plan_manifest, seed)
    _private_dir_empty(output)
    with (output / "trial_image_binding_NOT_APPROVED.csv").open(
            "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=BINDING_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary["binding_csv_sha256"] = sha256(
        (output / "trial_image_binding_NOT_APPROVED.csv").read_bytes()
    ).hexdigest()
    _write_json(output / "binding_manifest_NOT_APPROVED.json", summary)
    return summary


def operator_preview(root: Path, operator_acknowledged: bool) -> None:
    """Operator-only GUI; no timers, full-screen, image recording or response UI."""
    if not operator_acknowledged:
        raise ValueError("explicit --operator-only is mandatory for local monitor review")
    manifest, digest = open_candidate_set(root)
    # Tk and ImageTk are imported ONLY when an operator explicitly starts GUI.
    import tkinter as tk
    from PIL import Image, ImageTk

    entries = [
        (rec["word"], arm, root / rec["images"][arm]["path"])
        for rec in manifest["candidate_pairs"] for arm in ("X", "Y")
    ]
    app = tk.Tk()
    app.title("R13 — OPERATOR ONLY — Unapproved Images")
    app.configure(background="#343434")
    app.resizable(False, False)
    state = {"position": 0}

    banner = tk.Label(
        app, text="FOR OPERATOR IMAGE REVIEW ONLY — NO PARTICIPANTS",
        fg="#ffe5b5", bg="#343434",
        font=("Arial", 13, "bold"), padx=16, pady=10)
    banner.pack()
    info = tk.Label(app, text="", fg="white", bg="#343434",
                    font=("Arial", 12))
    info.pack(pady=5)
    img_label = tk.Label(app, bg="#343434")
    img_label.pack(padx=12, pady=6)
    status = tk.Label(
        app,
        text=f"Unapproved R12 candidate images | manifest SHA256 {digest[:16]}…\n"
             "NO timed play • NO human authorization • Esc to close",
        fg="#eeeeee", bg="#343434")
    status.pack()

    def show() -> None:
        word, arm, path = entries[state["position"]]
        with Image.open(path) as im:
            displayed = ImageTk.PhotoImage(im.convert("RGB"))
        img_label.configure(image=displayed)
        img_label.image = displayed  # retain photo
        info.configure(text=f"{state['position']+1} / 8  —  {word}  —  Condition {arm}")

    def move(shift: int) -> None:
        state["position"] = min(max(0, state["position"] + shift),
                                len(entries)-1)
        show()

    controls = tk.Frame(app, bg="#343434")
    controls.pack(pady=12)
    tk.Button(controls, text="Previous (manual)", width=20,
              command=lambda: move(-1)).pack(side="left", padx=7)
    tk.Button(controls, text="Next (manual)", width=20,
              command=lambda: move(+1)).pack(side="left", padx=7)
    tk.Button(controls, text="Close", width=12,
              command=app.destroy).pack(side="left", padx=7)
    app.bind("<Escape>", lambda _event: app.destroy())
    # No slideshow / no after() scheduling / no animation.
    show()
    app.mainloop()


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    pre = sub.add_parser("prepare-review", help="create pinned local all-pending checklist")
    pre.add_argument("--candidates", type=Path, required=True)
    pre.add_argument("--out", type=Path, required=True)
    inspect = sub.add_parser("inspect-operator", help="show stills only to the operator")
    inspect.add_argument("--candidates", type=Path, required=True)
    inspect.add_argument("--operator-only", action="store_true")
    bind = sub.add_parser("bind", help="create no-display balanced R10/12 trial mapping")
    bind.add_argument("--candidates", type=Path, required=True)
    bind.add_argument("--plan", type=Path, required=True)
    bind.add_argument("--plan-manifest", type=Path, required=True)
    bind.add_argument("--seed", required=True,
                      help="secret kept locally, not saved into mapping")
    bind.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare-review":
        value = prepare_review(args.candidates, args.out)
        print(json.dumps(value, sort_keys=True))
    elif args.command == "bind":
        value = write_binding(args.candidates, args.plan,
                              args.plan_manifest, args.seed, args.out)
        print(json.dumps(value, sort_keys=True))
    else:
        operator_preview(args.candidates, args.operator_only)


if __name__ == "__main__":
    main()
