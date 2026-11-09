"""R9 feasibility tests must never promote planning into measured eye evidence."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from evaluate_readiness import assess_inventory

TEMPLATE = Path(__file__).with_name("inventory_template.json")
SOURCE_HASH = "a" * 64


class FeasibilityTests(unittest.TestCase):
    def setUp(self):
        self.inventory = json.loads(TEMPLATE.read_text(encoding="utf-8"))

    def assess(self):
        return assess_inventory(self.inventory)

    def test_unknown_inventory_supports_only_document_work(self):
        result = self.assess()
        self.assertEqual(result["evidence_state"], "FEASIBILITY_ONLY_NO_OBSERVATIONS")
        self.assertTrue(result["readiness"]["P0_document_and_model_audit"])
        for name, ready in result["readiness"].items():
            if name != "P0_document_and_model_audit":
                self.assertFalse(ready, name)
        self.assertFalse(result["human_participant_testing_authorized"])
        self.assertFalse(result["automatic_procurement_authorized"])

    def test_external_SPD_requires_license_hash_and_provenance(self):
        spd = self.inventory["resources"]["published_spd"]
        spd.update({"access": "verified_access",
                    "source_url": "https://example.org/observed-other-monitor",
                    "source_sha256": SOURCE_HASH,
                    "license_note": "permitted for analysis",
                    "panel_match_note": "unrelated monitor, not calibrated to ours"})
        result = self.assess()
        self.assertTrue(result["readiness"]["P0_external_SPD_modeling_ready"])
        self.assertFalse(result["readiness"]["P2_own_monitor_emissive_SPD_capture_ready"])
        self.assertFalse(result["readiness"]["P3_objective_eye_study_planning_ready"])
        spd["source_sha256"] = "not-a-valid-hash"
        self.assertFalse(self.assess()["readiness"]["P0_external_SPD_modeling_ready"])

    def test_possible_loan_does_not_count_as_confirmed_colorimeter(self):
        self.inventory["monitor"].update({
            "access": "verified_access", "model": "Generic LCD 27",
            "settings_recorded": True})
        color = self.inventory["resources"]["colorimeter"]
        color.update({"access": "candidate_loan", "model": "calibrated meter",
                      "correction_reference": "proper CCSS"})
        self.assertFalse(self.assess()["readiness"]["P1_own_monitor_XYZ_EOTF_capture_ready"])
        color["access"] = "verified_access"
        self.assertTrue(self.assess()["readiness"]["P1_own_monitor_XYZ_EOTF_capture_ready"])
        self.assertFalse(self.assess()["readiness"]["P2_own_monitor_emissive_SPD_capture_ready"])

    def test_spectrometer_emission_mode_and_calibration_mandatory(self):
        self.inventory["monitor"].update({
            "access": "verified_access", "model": "External monitor",
            "settings_recorded": True})
        spec = self.inventory["resources"]["spectrometer"]
        spec.update({"access": "verified_access", "model": "Emissive spectrometer",
                     "emissive_mode_confirmed": False,
                     "calibration_record": "2026 lab calibration ticket"})
        self.assertFalse(self.assess()["readiness"]["P2_own_monitor_emissive_SPD_capture_ready"])
        spec["emissive_mode_confirmed"] = True
        self.assertTrue(self.assess()["readiness"]["P2_own_monitor_emissive_SPD_capture_ready"])
        self.assertFalse(self.assess()["human_participant_testing_authorized"])

    def test_objective_accommodation_needs_safety_and_oversight_not_just_device(self):
        mon = self.inventory["monitor"]
        mon.update({"access": "verified_access", "model": "Bench display",
                    "settings_recorded": True})
        spec = self.inventory["resources"]["spectrometer"]
        spec.update({"access": "verified_access", "model": "Emission reference",
                     "emissive_mode_confirmed": True,
                     "calibration_record": "traceable lab record"})
        instrument = self.inventory["resources"]["accommodation_instrument"]
        instrument.update({"access": "verified_access", "model": "Open-field autorefractor",
                           "operator_trained": True})
        self.assertFalse(self.assess()["readiness"]["P3_objective_eye_study_planning_ready"])
        self.inventory["human_research"].update({
            "ethics_approved": True, "supervisor_confirmed": True,
            "consent_protocol": True, "device_safety_reviewed": True})
        result = self.assess()
        self.assertTrue(result["readiness"]["P3_objective_eye_study_planning_ready"])
        # Feasibility is not authorization, even if all checklist items say true.
        self.assertFalse(result["human_participant_testing_authorized"])
        self.assertNotIn("MEASURED", result["evidence_state"])

    def test_reject_direct_observation_claims(self):
        for k in ("observations", "measured", "validated"):
            with self.subTest(k=k):
                data = deepcopy(self.inventory)
                data[k] = {"human_accommodation": "yes"}
                with self.assertRaises(ValueError):
                    assess_inventory(data)

    def test_reject_unverified_metadata_and_public_serial(self):
        self.inventory["monitor"]["access"] = "invented_status"
        with self.assertRaises(ValueError):
            self.assess()
        self.inventory["monitor"]["access"] = "unknown"
        self.inventory["monitor"]["serial_in_public_report"] = True
        with self.assertRaises(ValueError):
            self.assess()

    def test_reject_nonboolean_controls_and_missing_resource(self):
        self.inventory["human_research"]["ethics_approved"] = "true"
        with self.assertRaises(ValueError):
            self.assess()
        self.inventory["human_research"]["ethics_approved"] = False
        del self.inventory["resources"]["published_spd"]
        with self.assertRaises(ValueError):
            self.assess()

    def test_cli_creates_usable_json_without_network_or_instruments(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)/"readiness.json"
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("evaluate_readiness.py")),
                 "--inventory", str(TEMPLATE), "--out", str(out)],
                capture_output=True, text=True, check=True
            )
            result = json.loads(out.read_text())
            self.assertEqual(result["study"],
                             "GAZEBLOOM_R9_NO_PURCHASE_MEASUREMENT_READINESS_V1")
            self.assertEqual(result, json.loads(proc.stdout))
            self.assertFalse(result["readiness"]["P0_external_SPD_modeling_ready"])

    def test_requires_explicit_project_identity(self):
        self.inventory["project"] = "other"
        with self.assertRaises(ValueError):
            self.assess()


if __name__ == "__main__":
    unittest.main()
