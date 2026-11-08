"""Numerical invariants for synthetic directional templates (NOT eye responses)."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from evaluate import (
    SIGNS, VERSION, VARIANTS, fit_signed_pair, make_scene, run,
    scene_artifacts, score_profile, signed_alignment, swapped_channels,
    write_results, validation_profiles,
)


class AlignmentUnitTests(unittest.TestCase):
    def setUp(self):
        self.neg, self.pos = SIGNS
        r = np.random.default_rng(713)
        self.plus = r.normal(size=(3, 8, 8))
        self.minus = self.plus + r.normal(size=(3, 8, 8)) * .3
        self.target = {self.pos: self.plus, self.neg: self.minus}

    def test_perfect_has_score_one_and_both_signs_correct(self):
        measured = signed_alignment(self.target, self.target)
        self.assertAlmostEqual(measured["alignment"], 1., places=12)
        self.assertEqual(measured["correct_template_count"], 2)

    def test_reversal_has_negative_one(self):
        inverse = {self.pos: self.minus, self.neg: self.plus}
        measured = signed_alignment(inverse, self.target)
        self.assertAlmostEqual(measured["alignment"], -1., places=12)
        self.assertEqual(measured["correct_template_count"], 0)

    def test_identical_stimuli_have_zero_direction(self):
        same = {self.pos: self.plus, self.neg: self.plus}
        self.assertAlmostEqual(signed_alignment(same, self.target)["alignment"], 0.)

    def test_indistinguishable_targets_are_undefined_not_zero(self):
        t = {self.pos: self.plus, self.neg: self.plus}
        result = signed_alignment(self.target, t)
        self.assertIsNone(result["alignment"])
        self.assertIsNone(result["correct_template_count"])

    def test_reject_malformed_and_nonfinite(self):
        with self.assertRaises(ValueError):
            signed_alignment({self.pos: self.plus}, self.target)
        with self.assertRaises(ValueError):
            signed_alignment({self.pos: self.plus, self.neg: np.ones((3, 4, 4))},
                             self.target)
        with self.assertRaises(ValueError):
            signed_alignment({self.pos: np.full((3, 8, 8), np.nan),
                              self.neg: self.minus}, self.target)


class MatchedCapacityTests(unittest.TestCase):
    def test_rb_swap_preserves_values_pixel_means_chroma_saturation(self):
        scene = make_scene("original_texture", 64)
        rng = np.random.default_rng(19)
        rgb = rng.uniform(0, 1, (3, 64, 64))
        rgb[:, 0, 0] = (0, 1, 0)
        permuted = swapped_channels(rgb)
        np.testing.assert_array_equal(permuted[0], rgb[2])
        np.testing.assert_array_equal(permuted[1], rgb[1])
        np.testing.assert_allclose(permuted.mean(axis=0), rgb.mean(axis=0))
        np.testing.assert_array_equal(np.sort(permuted.ravel()), np.sort(rgb.ravel()))
        p = scene_artifacts(scene, rgb)
        q = scene_artifacts(scene, permuted)
        for key in ("mean_abs_chroma", "edge_chroma_mean", "saturated_channel_fraction"):
            self.assertAlmostEqual(p[key], q[key], places=13)

    def test_rb_swap_is_involution(self):
        x = np.arange(3*8*8, dtype=float).reshape((3, 8, 8))
        np.testing.assert_array_equal(swapped_channels(swapped_channels(x)), x)
        with self.assertRaises(ValueError):
            swapped_channels(x[0])

    def test_scene_artifact_proxy_is_zero_for_achromatic(self):
        scene = make_scene("synthetic_letter_edges", 64)
        same = np.broadcast_to(scene, (3, 64, 64)).copy()
        proxy = scene_artifacts(scene, same)
        self.assertAlmostEqual(proxy["mean_abs_chroma"], 0, places=12)
        self.assertAlmostEqual(proxy["edge_chroma_mean"], 0, places=12)


class SmallRunTests(unittest.TestCase):
    def test_single_scene_profile_produces_complete_nonclinical_record(self):
        rows, summary = run(
            scenes=("original_texture",),
            profiles=(validation_profiles()[0],),
            size=64, maxiter=90)
        self.assertEqual(len(rows), 1)
        self.assertEqual(summary["study"], VERSION)
        self.assertEqual(summary["defined_directional_rows"], 1)
        for metric in ("rgb_alignment", "rb_swap_alignment", "gray_alignment"):
            self.assertTrue(np.isfinite(rows[0][metric]))
        self.assertEqual(rows[0]["scope"],
                         "SYNTHETIC_DIRECTIONAL_TEMPLATE_SCORE_ONLY")
        self.assertEqual(set(VARIANTS),
                         {"unmodified", "gray", "rgb", "rgb_rb_swapped"})
        self.assertEqual(summary["verdict"],
                         "DIAGNOSTIC_ONLY_NO_ACCOMMODATION_CLAIM")
        with tempfile.TemporaryDirectory() as p:
            write_results(Path(p), rows, summary)
            self.assertEqual({x.name for x in Path(p).iterdir()},
                             {"direction.csv", "summary.json", "manifest.json"})
            record = json.loads((Path(p)/"summary.json").read_text())
            self.assertEqual(record["rows"], 1)
            hashes = json.loads((Path(p)/"manifest.json").read_text())["source_sha256"]
            self.assertEqual(len(hashes), 4)
            self.assertTrue(all(len(v) == 64 for v in hashes.values()))

    def test_reject_odd_size_and_invalid_iteration_count(self):
        with self.assertRaises(ValueError):
            run(size=63)
        with self.assertRaises(ValueError):
            run(maxiter=0)


if __name__ == "__main__":
    unittest.main()
