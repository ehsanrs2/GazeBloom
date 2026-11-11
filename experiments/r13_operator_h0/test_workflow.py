"""R13 H0 operator-only workflow; no real monitor, camera or human I/O in CI."""
from __future__ import annotations

from copy import deepcopy
import csv
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from workflow import (
    BINDING_FIELDS, STUDY, bind_pairs, open_candidate_set,
    operator_preview, prepare_review, verify_pair_balance, write_binding,
)
from generate_candidates import SCENES, export as r12_export
from pilot import make_plan as r10_make_plan, _write_csv, PLAN_FIELDS


class R13OfflineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.candidates = self.root / "r12"
        self.manifest = r12_export(self.candidates)
        self.plan, self.plan_manifest = r10_make_plan("P000", "ci-no-participant-seed")

    def test_01_exact_image_provenance_and_no_H1_approval(self):
        a, digest = open_candidate_set(self.candidates)
        self.assertEqual(a, self.manifest)
        self.assertEqual(digest, sha256(
            (self.candidates/"manifest.json").read_bytes()).hexdigest())
        self.assertFalse(a["human_exposure_authorized"])
        self.assertTrue(all(not p["human_display_approved"]
                            for p in a["candidate_pairs"]))

    def test_02_prepared_review_pin_is_pending_and_not_authorization(self):
        out = self.root / "private_review"
        report = prepare_review(self.candidates, out)
        self.assertEqual(
            report["review_state"], "PENDING_REVIEW_NO_HUMAN_EXPOSURE")
        # Automatically pinning provenance is NOT viewing the actual monitor.
        self.assertEqual(report["checkpoints_completed"], 1)
        self.assertFalse(report["human_exposure_authorized"])
        review = json.loads((out/"review_PENDING.json").read_text())
        self.assertFalse(review["real_display"]["operator_viewed_actual_monitor"])
        self.assertTrue(all(
            check == "pending"
            for p in review["per_pair"].values() for check in p.values()))
        self.assertFalse(review["participant_safeguards"][
            "informed_consent_plan_reviewed"])
        self.assertEqual(len(list(out.iterdir())),3)
        self.assertFalse(json.loads(
            (out/"operator_instructions.json").read_text())[
            "human_exposure_authorized"])

    def test_03_review_preparation_refuses_overwrite(self):
        out = self.root / "private_review"
        prepare_review(self.candidates, out)
        with self.assertRaises(FileExistsError):
            prepare_review(self.candidates, out)

    def test_04_tampered_png_prevents_preview_and_preparation(self):
        r = self.manifest["candidate_pairs"][0]["images"]["X"]
        with (self.candidates/r["path"]).open("ab") as f:
            f.write(b"changed")
        with self.assertRaises(ValueError):
            open_candidate_set(self.candidates)
        with self.assertRaises(ValueError):
            prepare_review(self.candidates, self.root/"review")

    def test_05_no_GUI_without_explicit_operator_flag(self):
        # No Tcl/Tk display is required: rejection occurs before Tk imports.
        with self.assertRaisesRegex(ValueError,"--operator-only"):
            operator_preview(self.candidates, operator_acknowledged=False)

    def test_06_four_words_each_XY_once_and_four_positions_apart(self):
        rows, info = bind_pairs(self.candidates, self.plan, self.plan_manifest,
                                "private-binding-seed-2026")
        self.assertEqual(info["study"], STUDY)
        self.assertEqual(len(rows), 8)
        self.assertEqual(set(r["word"] for r in rows), set(SCENES))
        self.assertEqual(len({r["trial_id"] for r in rows}),8)
        self.assertTrue(info["each_word_once_per_condition"])
        self.assertEqual(info["repeat_separation_trials"],4)
        self.assertFalse(info["human_exposure_authorized"])
        self.assertFalse(info["camera_required"])
        self.assertFalse(info["participant_responses_present"])
        for i in range(4):
            self.assertEqual(rows[i]["word"], rows[i+4]["word"])
            self.assertNotEqual(rows[i]["condition_code"],
                                rows[i+4]["condition_code"])
        for r in rows:
            original=next(x for x in self.manifest["candidate_pairs"]
                          if x["word"]==r["word"])["images"][r["condition_code"]]
            self.assertEqual(r["image_sha256"],original["sha256"])
            self.assertEqual(r["image_relative_path"],original["path"])
            self.assertEqual(r["max_view_seconds"],"10")
            self.assertEqual(r["min_rest_seconds"],"30")

    def test_07_binding_is_deterministic_and_pseudonym_or_seed_changes_order(self):
        a,_=bind_pairs(self.candidates,self.plan,self.plan_manifest,
                       "private-binding-seed-2026")
        b,_=bind_pairs(self.candidates,self.plan,self.plan_manifest,
                       "private-binding-seed-2026")
        self.assertEqual(a,b)
        all_orders=set()
        for i in range(12):
            rows,_=bind_pairs(self.candidates,self.plan,self.plan_manifest,
                              f"private-binding-seed-{i:04d}")
            all_orders.add(tuple(x["word"] for x in rows[:4]))
        self.assertGreater(len(all_orders),1)
        self.assertEqual(len(all_orders)<=24,True)

    def test_08_complementary_R10_condition_schedule_also_valid(self):
        # R10 may flip condition signs per pseudonym; both orientations work.
        flip=deepcopy(self.plan)
        for r in flip:
            r["condition_code"]="Y" if r["condition_code"]=="X" else "X"
        rows,_=bind_pairs(self.candidates,flip,self.plan_manifest,
                          "private-binding-seed-2026")
        verify_pair_balance(rows)
        self.assertEqual({r["condition_code"] for r in rows},{"X","Y"})

    def test_09_corrupt_R10_schedule_or_consent_flags_are_rejected(self):
        examples = []
        x=deepcopy(self.plan)
        x[4]["condition_code"]=x[0]["condition_code"]
        examples.append((x,deepcopy(self.plan_manifest)))
        x=deepcopy(self.plan)
        x[3]["trial_id"]="T01"
        examples.append((x,deepcopy(self.plan_manifest)))
        x=deepcopy(self.plan)
        x[0]["max_view_seconds"]="999"
        examples.append((x,deepcopy(self.plan_manifest)))
        m=deepcopy(self.plan_manifest)
        m["human_test_authorized_by_script"]=True
        examples.append((deepcopy(self.plan),m))
        m=deepcopy(self.plan_manifest)
        m["camera_required"]=True
        examples.append((deepcopy(self.plan),m))
        for j,(x,m) in enumerate(examples):
            with self.subTest(case=j),self.assertRaises(ValueError):
                bind_pairs(self.candidates,x,m,"private-binding-seed-2026")

    def test_10_seed_must_be_nontrivial_and_not_written_in_output(self):
        with self.assertRaises(ValueError):
            bind_pairs(self.candidates,self.plan,self.plan_manifest,"short")
        out=self.root/"binding"
        plan_file=self.root/"trials.csv"
        manifest_file=self.root/"r10_manifest.json"
        _write_csv(plan_file, PLAN_FIELDS,self.plan)
        manifest_file.write_text(json.dumps(self.plan_manifest))
        report=write_binding(self.candidates,plan_file,manifest_file,
                             "do-not-export-this-secret-2026",out)
        self.assertEqual(report["planned_trial_count"],8)
        self.assertFalse(report["human_exposure_authorized"])
        csv_data=(out/"trial_image_binding_NOT_APPROVED.csv").read_text()
        self.assertNotIn("do-not-export-this-secret-2026",csv_data)
        metadata=(out/"binding_manifest_NOT_APPROVED.json").read_text()
        self.assertNotIn("do-not-export-this-secret-2026",metadata)
        with (out/"trial_image_binding_NOT_APPROVED.csv").open() as f:
            self.assertEqual(len(list(csv.DictReader(f))),8)
        self.assertEqual(len(list(out.iterdir())),2)

    def test_11_no_binding_overwrite(self):
        plan_file=self.root/"trials.csv"
        manifest_file=self.root/"r10_manifest.json"
        _write_csv(plan_file,PLAN_FIELDS,self.plan)
        manifest_file.write_text(json.dumps(self.plan_manifest))
        out=self.root/"bound"
        write_binding(self.candidates,plan_file,manifest_file,
                      "private-binding-seed-2026",out)
        with self.assertRaises(FileExistsError):
            write_binding(self.candidates,plan_file,manifest_file,
                          "private-binding-seed-2026",out)

    def test_12_manual_balance_check_rejects_wrong_scene_assignment(self):
        rows,_=bind_pairs(self.candidates,self.plan,self.plan_manifest,
                          "private-binding-seed-2026")
        tampered=deepcopy(rows)
        tampered[4]["word"]="WRONG"
        with self.assertRaises(ValueError):
            verify_pair_balance(tampered)
        tampered=deepcopy(rows)
        tampered[1]["trial_id"]=tampered[0]["trial_id"]
        with self.assertRaises(ValueError):
            verify_pair_balance(tampered)

    def test_13_cli_prepare_only_writes_pending_documentation(self):
        command=[
            sys.executable,str(Path(__file__).with_name("workflow.py")),
            "prepare-review","--candidates",str(self.candidates),
            "--out",str(self.root/"h0")
        ]
        result=subprocess.run(command,check=True,capture_output=True,text=True)
        report=json.loads(result.stdout)
        self.assertEqual(report["review_state"],
                         "PENDING_REVIEW_NO_HUMAN_EXPOSURE")
        self.assertFalse(report["human_exposure_authorized"])
        self.assertEqual(report["checkpoints_completed"],1)

    def test_14_default_cli_never_launches_GUI_or_camera(self):
        cmd=[
            sys.executable,str(Path(__file__).with_name("workflow.py")),
            "inspect-operator","--candidates",str(self.candidates)
        ]
        result=subprocess.run(cmd,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn("--operator-only",result.stderr)


if __name__=="__main__":
    unittest.main()
