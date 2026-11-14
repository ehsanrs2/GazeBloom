"""R15: governance inputs are never a machine-created authorization."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from readiness import R12_SHA, R12_PENDING, STUDY, audit

HERE=Path(__file__).resolve().parent


def fake_r12(completed: int = 20) -> dict:
    remaining=sorted(R12_PENDING)
    if completed != 20:
        remaining=remaining[:25-completed]
    return {
        "study":"GAZEBLOOM_R12_STATIC_CONTRAST_SAFETY_PREVIEW_V1",
        "checkpoints_completed":completed,
        "checkpoints_total":25,
        "remaining_checks":remaining,
        "source_manifest_sha256":R12_SHA,
        "human_exposure_authorized":False,
        "phone_recording_authorized":False,
        "human_data_collected":False,
    }


def template() -> dict:
    return json.loads((HERE/"readiness_template.json").read_text(encoding="utf-8"))


class GovernanceAudit(unittest.TestCase):
    def test_pending_template_is_never_approved(self):
        r=audit(fake_r12(),template())
        self.assertEqual(r["study"],STUDY)
        self.assertEqual(r["r12_checkpoints"],"20/25")
        self.assertEqual(set(r["r12_unresolved"]),R12_PENDING)
        self.assertEqual(
            r["operator_r14_demo"],"FUNCTION_REPORTED_PASS__NO_LATENCY_MEASUREMENT")
        self.assertFalse(r["human_exposure_authorized"])
        self.assertFalse(r["phone_recording_authorized"])
        self.assertFalse(r["human_study_data_collected"])
        self.assertFalse(r["measured_accommodation"])
        self.assertIn("actual_H1_runner_and_stop_validation_NOT_PRESENT",
                      r["unresolved_reasons"])

    def test_complete_fake_governance_cannot_grant_human_exposure(self):
        f=template()
        f["jurisdiction"]={"country":"ExampleCountry","study_context":"independent"}
        f["ethics"]={
            "review_status":"reviewed",
            "competent_authority_reference":"TEST_AUTHORITY_NOT_REAL",
            "decision_reference":"TEST_DECISION_NOT_REAL",
            "formal_approval_if_required":True,
        }
        f["consent"]={
            "review_status":"reviewed",
            "final_document_sha256":"a"*64,
            "review_reference":"TEST_CONSENT_NOT_REAL",
        }
        f["privacy"]={
            "review_status":"reviewed",
            "data_controller_reference":"TEST_OPERATOR_NOT_REAL",
            "retention_days":30,
            "deletion_policy_reference":"TEST_POLICY_NOT_REAL",
        }
        f["human_stop"]={
            "review_status":"reviewed",
            "real_participant_runner_test_report":"TEST_STOP_REPORT_NOT_REAL",
        }
        f["optional_camera"]={
            "camera_off_by_default":True,
            "review_status":"reviewed",
            "separate_consent_policy_reference":"TEST_OPTIONAL_NO_CAMERA",
        }
        r=audit(fake_r12(25),f)
        self.assertFalse(r["human_exposure_authorized"])
        self.assertIn(
            "independent_human_participant_runner_authorization_NOT_IMPLEMENTED",
            r["unresolved_reasons"],
        )
        self.assertEqual(r["decision"],
                         "H1_NOT_AUTHORIZED__GOVERNANCE_AND_REAL_RUNNER_PENDING")

    def test_invented_operator_latency_or_human_exposure_flag_rejected(self):
        for key,v in (("measured_stop_latency_ms",1.),
                      ("real_human_stimuli_displayed",True),
                      ("reported_functional",False)):
            f=template()
            f["operator_r14_demo"][key]=v
            with self.subTest(key=key),self.assertRaises(ValueError):
                audit(fake_r12(),f)
        f=template()
        f["human_exposure_requested"]=True
        with self.assertRaises(ValueError):
            audit(fake_r12(),f)

    def test_camera_must_remain_off(self):
        f=template()
        f["optional_camera"]["camera_off_by_default"]=False
        with self.assertRaisesRegex(ValueError,"camera must be off"):
            audit(fake_r12(),f)

    def test_r12_original_sha_and_no_human_flags_required(self):
        for key,v in (("source_manifest_sha256","f"*64),
                      ("human_exposure_authorized",True),
                      ("human_data_collected",True),
                      ("phone_recording_authorized",True)):
            m=fake_r12()
            m[key]=v
            with self.subTest(key=key),self.assertRaises(ValueError):
                audit(m,template())

    def test_r12_status_inconsistency_rejected(self):
        m=fake_r12()
        m["remaining_checks"]=[]
        with self.assertRaises(ValueError):
            audit(m,template())
        m=fake_r12()
        m["checkpoints_completed"]=True
        with self.assertRaises(ValueError):
            audit(m,template())

    def test_unhashable_remaining_check_is_rejected_cleanly(self):
        m=fake_r12()
        m["remaining_checks"][0]={"unexpected":"nested"}
        with self.assertRaisesRegex(ValueError,"incoherent R12"):
            audit(m,template())

    @unittest.skipUnless(os.name == "posix", "POSIX file permissions")
    def test_private_report_exclusive_creation_and_mode(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"r12.json").write_text(json.dumps(fake_r12()),encoding="utf-8")
            (root/"form.json").write_text(json.dumps(template()),encoding="utf-8")
            out=root/"private"/"status.json"
            cmd=[sys.executable,str(HERE/"readiness.py"),
                 "--r12-report",str(root/"r12.json"),
                 "--form",str(root/"form.json"),"--out",str(out)]
            subprocess.run(cmd,check=True,capture_output=True,text=True)
            self.assertEqual(out.stat().st_mode & 0o777,0o600)
            self.assertEqual(out.parent.stat().st_mode & 0o777,0o700)
            original=out.read_bytes()
            repeat=subprocess.run(cmd,capture_output=True,text=True)
            self.assertNotEqual(repeat.returncode,0)
            self.assertEqual(out.read_bytes(),original)
            out.unlink()
            target=root/"target.txt"
            target.write_text("DO NOT CHANGE",encoding="utf-8")
            out.symlink_to(target)
            linked=subprocess.run(cmd,capture_output=True,text=True)
            self.assertNotEqual(linked.returncode,0)
            self.assertEqual(target.read_text(encoding="utf-8"),"DO NOT CHANGE")

    def test_pending_ethics_country_must_not_be_implied(self):
        f=template()
        result=audit(fake_r12(),f)
        self.assertIn("study_country_and_institutional_context_UNSPECIFIED",
                      result["unresolved_reasons"])
        self.assertIn("real_ethics_determination_PENDING",
                      result["unresolved_reasons"])

    def test_invalid_status_and_placeholder_data_rejected_or_pending(self):
        f=template()
        f["privacy"]["review_status"]="pass"
        with self.assertRaises(ValueError):
            audit(fake_r12(),f)
        f=template()
        f["jurisdiction"]["country"]="TBD"
        with self.assertRaises(ValueError):
            audit(fake_r12(),f)

    def test_reviewed_without_actual_references_does_not_pass_gap(self):
        f=template()
        f["jurisdiction"]={"country":"Testland","study_context":"independent"}
        f["ethics"]["review_status"]="reviewed"
        f["consent"]["review_status"]="reviewed"
        f["privacy"]["review_status"]="reviewed"
        f["human_stop"]["review_status"]="reviewed"
        f["optional_camera"]["review_status"]="reviewed"
        r=audit(fake_r12(),f)
        for reason in (
            "ethics_review_reference_OR_jurisdiction_MISSING",
            "final_consent_review_evidence_MISSING",
            "data_controller_retention_deletion_review_MISSING",
            "actual_H1_runner_and_stop_validation_NOT_PRESENT",
            "phone_separate_consent_review_PENDING__PHONE_REMAINS_OFF",
        ):
            self.assertIn(reason,r["unresolved_reasons"])

    def test_rejected_governance_is_exposed(self):
        f=template()
        f["ethics"]["review_status"]="rejected"
        r=audit(fake_r12(),f)
        self.assertIn("at_least_one_governance_gate_REJECTED",
                      r["unresolved_reasons"])
        self.assertFalse(r["human_exposure_authorized"])

    def test_cli_dry_run_writes_once_and_no_private_names_in_public_output(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"r12.json").write_text(json.dumps(fake_r12()),encoding="utf-8")
            (root/"form.json").write_text(json.dumps(template()),encoding="utf-8")
            out=root/"status.json"
            cmd=[sys.executable,str(HERE/"readiness.py"),
                 "--r12-report",str(root/"r12.json"),
                 "--form",str(root/"form.json"),"--out",str(out)]
            r=subprocess.run(cmd,check=True,capture_output=True,text=True)
            self.assertEqual(json.loads(r.stdout),json.loads(out.read_text()))
            self.assertFalse(json.loads(r.stdout)["human_exposure_authorized"])
            second=subprocess.run(cmd,capture_output=True,text=True)
            self.assertNotEqual(second.returncode,0)
            self.assertIn("refuse overwrite",second.stderr)


if __name__=="__main__":
    unittest.main()
