"""R11 still-only, low-chroma numeric gate and reproducible artifact tests."""
from __future__ import annotations

import csv
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from generate import (CONDITIONS, L_BACKGROUND, L_FOREGROUND,
                      MAX_PROXY_LUMINANCE_MISMATCH, MAX_SRGB_CHANNEL_SPREAD,
                      SCENES, SIZE, STUDY, export, generate_pair, label_mask,
                      linear_to_srgb, srgb_to_linear)


class StaticPairTests(unittest.TestCase):
    def test_exactly_four_distinct_large_word_scenes(self):
        self.assertEqual(len(SCENES),4)
        self.assertEqual(len(set(SCENES)),4)
        self.assertEqual(CONDITIONS,("X","Y"))
        self.assertEqual(SIZE,(640,360))
        self.assertEqual((L_BACKGROUND,L_FOREGROUND),(.54,.37))
        self.assertGreater(min(len(word) for word in SCENES),2)

    def test_source_scene_motif_is_large_and_nonempty(self):
        arrays=[np.array(label_mask(word)) for word in SCENES]
        for a in arrays:
            self.assertEqual(a.shape,(SIZE[1],SIZE[0]))
            self.assertGreater(np.count_nonzero(a),1000)
            self.assertEqual(a.min(),0)
            self.assertEqual(a.max(),255)
        self.assertFalse(np.array_equal(arrays[0],arrays[1]))

    def test_all_pairs_preserve_model_luminance_after_8bit_roundtrip(self):
        for word in SCENES:
            with self.subTest(word=word):
                x,y,stats=generate_pair(word)
                self.assertEqual(x.shape,(360,640,3))
                self.assertEqual(x.dtype,np.uint8)
                self.assertEqual(y.dtype,np.uint8)
                self.assertTrue(np.array_equal(x[:,:,0],x[:,:,1]))
                self.assertTrue(np.array_equal(x[:,:,0],x[:,:,2]))
                self.assertLessEqual(stats["max_quantized_srgb_proxy_luminance_mismatch"],
                                     MAX_PROXY_LUMINANCE_MISMATCH)
                self.assertLess(stats["max_intended_linear_luminance_mismatch"],1e-12)
                self.assertGreater(stats["pixels_with_any_condition_difference"],2000)
                self.assertLessEqual(stats["max_colored_srgb_channel_spread_8bit"],
                                     MAX_SRGB_CHANNEL_SPREAD)
                self.assertGreaterEqual(stats["min_srgb_code"],100)
                self.assertLessEqual(stats["max_srgb_code"],220)

    def test_not_achromatically_identical_but_mild_color(self):
        x,y,_=generate_pair(SCENES[0])
        self.assertGreater(np.count_nonzero(x!=y),5000)
        self.assertGreater(np.max(np.abs(y[:,:,0].astype(int)-y[:,:,1].astype(int))),1)
        self.assertLessEqual(np.max(np.abs(y[:,:,0].astype(int)-y[:,:,1].astype(int))),11)

    def test_srgb_conversion_roundtrip_in_valid_range(self):
        a=np.linspace(0,1,200)
        np.testing.assert_allclose(srgb_to_linear(linear_to_srgb(a)),
                                   a,rtol=1e-12,atol=1e-12)
        with self.assertRaises(ValueError):
            linear_to_srgb(np.array([-0.1,.5]))
        with self.assertRaises(ValueError):
            srgb_to_linear(np.array([float("nan")]))

    def test_reject_unregistered_scene(self):
        with self.assertRaises(ValueError):
            label_mask("UNSAFE_NONREGISTERED")
        with self.assertRaises(ValueError):
            generate_pair("AAAAA")


class ArtifactAndNoExposureTests(unittest.TestCase):
    def test_export_images_manifest_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"review"
            manifest=export(out)
            self.assertEqual(manifest["study"],STUDY)
            self.assertEqual(len(manifest["scenes"]),4)
            self.assertFalse(manifest["human_exposure_authorized"])
            self.assertFalse(manifest["human_participant_images_displayed"])
            self.assertFalse(manifest["human_accommodation_measured"])
            self.assertFalse(manifest["experimental_chromablur_efficacy_claim"])
            self.assertTrue(manifest["all_still_images"])
            self.assertFalse(manifest["animated_or_flashing_content"])
            self.assertIn("MANUAL_SAFETY_AND_ETHICS_PENDING",manifest["review_state"])
            pairs=list(csv.DictReader((out/"operator_pairs.csv").open()))
            self.assertEqual(len(pairs),4)
            self.assertEqual(len(list((out/"candidates_not_approved").glob("*.png"))),8)
            for scene in manifest["scenes"]:
                self.assertFalse(scene["operator_reviewed"])
                self.assertFalse(scene["approved_for_participant_display"])
                for x in scene["files"].values():
                    file=out/x["file"]
                    self.assertEqual(sha256(file.read_bytes()).hexdigest(),x["sha256"])
                    with Image.open(file) as image:
                        self.assertEqual(image.size,SIZE)
                        self.assertEqual(image.format,"PNG")
                        self.assertEqual(image.mode,"RGB")
                        self.assertEqual(getattr(image,"n_frames",1),1)
            data=json.loads((out/"audit_manifest.json").read_text())
            self.assertEqual(data,manifest)

    def test_repeat_export_is_identical_inside_same_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/"a"
            b=Path(tmp)/"b"
            x=export(a)
            y=export(b)
            self.assertEqual(x,y)
            a_files={p.relative_to(a):sha256(p.read_bytes()).hexdigest()
                     for p in a.rglob("*") if p.is_file()}
            b_files={p.relative_to(b):sha256(p.read_bytes()).hexdigest()
                     for p in b.rglob("*") if p.is_file()}
            self.assertEqual(a_files,b_files)

    def test_refuse_overwriting_previous_candidate_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"data"
            export(out)
            with self.assertRaises(FileExistsError):
                export(out)

    def test_manifest_has_no_participant_identity_or_responses(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest=export(Path(tmp)/"preview")
            raw=json.dumps(manifest)
            for key in ("participant_id","participant_code","camera_video",
                        "human_eye_diameter","accommodation_diopters","face_image"):
                self.assertNotIn(key,raw)
            self.assertEqual(manifest["condition_X"],
                             "grayscale large-word static image")


if __name__=="__main__":
    unittest.main()
