"""R12: human-display review is never authorized by software alone."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from generate_candidates import (
    STUDY, SCENES, REFERENCE_LARGE_TEXT_CONTRAST, BACKGROUND_LINEAR,
    TEXT_LINEAR, generate_pair, export, contrast_ratio,
)
from review_gate import assess, verify_artifact

TEMPLATE = Path(__file__).with_name("review_template.json")


class CandidateContrastTests(unittest.TestCase):
    def test_correctable_r11_baseline_below_three_r12_above(self):
        self.assertLess(contrast_ratio(.37,.54),1.5)
        self.assertGreater(contrast_ratio(TEXT_LINEAR,BACKGROUND_LINEAR),3.)
        self.assertEqual(REFERENCE_LARGE_TEXT_CONTRAST,3.)
        with self.assertRaises(ValueError):
            contrast_ratio(-.1,.6)

    def test_four_pairs_have_subtle_chroma_and_better_core_legibility(self):
        self.assertEqual(len(SCENES),4)
        for word in SCENES:
            with self.subTest(word=word):
                x,y,m=generate_pair(word)
                self.assertEqual(x.shape,(360,640,3))
                self.assertEqual(y.shape,x.shape)
                self.assertEqual(x.dtype,np.uint8)
                self.assertGreaterEqual(
                    min(m["modeled_core_large_text_contrast_X"],
                        m["modeled_core_large_text_contrast_Y"]),3.)
                self.assertLessEqual(m["model_postquantized_luminance_mismatch"],.008)
                self.assertLessEqual(m["max_8bit_rgb_channel_spread_Y"],11)
                self.assertGreaterEqual(m["changed_pixels_X_vs_Y"],2500)
                self.assertTrue(np.array_equal(x[:,:,0],x[:,:,1]))
                self.assertFalse(np.array_equal(x,y))

    def test_repeatability_and_no_animations_or_human_status(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/"a"
            b=Path(td)/"b"
            x=export(a)
            y=export(b)
            self.assertEqual(x,y)
            self.assertFalse(x["human_exposure_authorized"])
            self.assertFalse(x["human_participants_tested"])
            self.assertFalse(x["real_display_luminance_measured"])
            self.assertIn("PENDING",x["review"])
            for rec in x["candidate_pairs"]:
                self.assertFalse(rec["human_display_approved"])
                for info in rec["images"].values():
                    p=a/info["path"]
                    self.assertEqual(sha256(p.read_bytes()).hexdigest(),info["sha256"])
                    self.assertEqual(p.read_bytes(),(b/info["path"]).read_bytes())
                    with Image.open(p) as im:
                        self.assertEqual(im.mode,"RGB")
                        self.assertEqual(im.format,"PNG")
                        self.assertEqual(im.size,(640,360))
                        self.assertEqual(getattr(im,"n_frames",1),1)
            with self.assertRaises(FileExistsError):
                export(a)


class ReviewGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.manifest=export(self.root/"new")
        self.images=self.root/"new"
        self.review=json.loads(TEMPLATE.read_text(encoding="utf-8"))

    def test_default_template_cannot_approve_humans(self):
        result=assess(self.manifest,self.review,self.images)
        self.assertEqual(result["review_state"],"PENDING_REVIEW_NO_HUMAN_EXPOSURE")
        self.assertEqual(result["checkpoints_completed"],0)
        self.assertEqual(result["pair_count"],4)
        self.assertFalse(result["human_exposure_authorized"])
        self.assertFalse(result["phone_recording_authorized"])
        self.assertFalse(result["human_data_collected"])
        self.assertFalse(result["measured_accommodation"])

    def test_sha256_mismatch_rejects_tampered_png(self):
        f=self.images/self.manifest["candidate_pairs"][0]["images"]["X"]["path"]
        f.write_bytes(f.read_bytes()+b"x")
        with self.assertRaisesRegex(ValueError,"digest mismatch"):
            verify_artifact(self.images,self.manifest)

    def test_tampered_operator_index_is_rejected(self):
        index=self.images/"operator_index.csv"
        index.write_bytes(index.read_bytes()+b"junk")
        with self.assertRaisesRegex(ValueError,"operator index"):
            assess(self.manifest,self.review,self.images)

    def test_correctly_completed_checklist_is_only_administrative(self):
        r=self.review
        r["reviewed_manifest_sha256"]=sha256(
            (self.images/"manifest.json").read_bytes()).hexdigest()
        r["real_display"].update({
            "operator_viewed_actual_monitor":True,
            "display_alias":"internal-display-A",
            "brightness_comfortable":"pass",
            "stable_ambient_light":"pass",
            "hdr_and_nightlight_not_changed_during_review":"pass",
            "static_only_without_flashing_or_flicker":"pass",
        })
        for w in SCENES:
            r["per_pair"][w]={k:"pass" for k in ("legibility","color_comfort","pattern_risk")}
        r["participant_safeguards"].update({
            "locally_applicable_ethics_determination":"pass",
            "review_reference":"TEST-ONLY-do-not-use-as-approval",
            "informed_consent_plan_reviewed":True,
            "immediate_stop_mechanism_reviewed":True,
            "privacy_and_retention_plan_reviewed":True,
            "optional_phone_separate_consent_reviewed":True,
        })
        result=assess(self.manifest,r,self.images)
        self.assertEqual(result["checkpoints_completed"],result["checkpoints_total"])
        self.assertEqual(result["remaining_checks"],[])
        self.assertEqual(
            result["review_state"],
            "ADMINISTRATIVE_REVIEW_COMPLETE__SEPARATE_AUTHORIZATION_REQUIRED")
        self.assertFalse(result["human_exposure_authorized"])

    def test_real_image_and_ethics_fail_flags_reject(self):
        for category in ("real_display","per_pair","participant_safeguards"):
            with self.subTest(category=category):
                r=deepcopy(self.review)
                if category=="real_display":
                    r[category]["brightness_comfortable"]="fail"
                elif category=="per_pair":
                    r[category]["NOVA"]["pattern_risk"]="fail"
                else:
                    r[category]["locally_applicable_ethics_determination"]="fail"
                result=assess(self.manifest,r,self.images)
                self.assertEqual(result["review_state"],"REJECTED_BY_OPERATOR")

    def test_stale_or_malformed_manifest_digest_rejected(self):
        for digest in ("0"*64,"broken",42):
            with self.subTest(digest=digest):
                r=deepcopy(self.review)
                r["reviewed_manifest_sha256"]=digest
                with self.assertRaises(ValueError):
                    assess(self.manifest,r,self.images)

    def test_unapproved_flags_cannot_be_overridden(self):
        for key in ("human_exposure_requested","public_media_or_participant_data"):
            r=deepcopy(self.review)
            r[key]=True
            with self.subTest(key=key),self.assertRaises(ValueError):
                assess(self.manifest,r,self.images)
        r=deepcopy(self.review)
        r["participant_safeguards"]["camera_off_by_default"]=False
        with self.assertRaises(ValueError):
            assess(self.manifest,r,self.images)

    def test_unknown_state_or_missing_pair_is_invalid(self):
        r=deepcopy(self.review)
        r["real_display"]["brightness_comfortable"]="safe"
        with self.assertRaises(ValueError):
            assess(self.manifest,r,self.images)
        r=deepcopy(self.review)
        del r["per_pair"]["TORA"]
        with self.assertRaises(ValueError):
            assess(self.manifest,r,self.images)

    def test_manifest_path_traversal_and_nonapproved_labels_rejected(self):
        m=deepcopy(self.manifest)
        m["candidate_pairs"][0]["images"]["X"]["path"]="../secret.png"
        with self.assertRaises(ValueError):
            verify_artifact(self.images,m)
        m=deepcopy(self.manifest)
        m["candidate_pairs"][0]["human_display_approved"]=True
        with self.assertRaises(ValueError):
            verify_artifact(self.images,m)

    def test_human_claims_in_manifest_not_accepted(self):
        for key in ("human_exposure_authorized","human_participants_tested"):
            m=deepcopy(self.manifest)
            m[key]=True
            with self.subTest(key=key),self.assertRaises(ValueError):
                verify_artifact(self.images,m)


if __name__=="__main__":
    unittest.main()
