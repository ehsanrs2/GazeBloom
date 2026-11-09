"""Tests for preregistered, non-physiological R8 numerical comparisons."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from evaluate import (
    CASES, CURVE_FLAT_REL, FINE_FOCUS_D, METRICS, MODELS, PEAK_TIE_REL,
    SCENES, STRIDES, STUDY, SpectralCase, describe_peak, execute,
    focus_metrics, make_r8_scene, shifted_otfs, write_outputs,
)


class FrozenProtocolTests(unittest.TestCase):
    def test_all_sensitivity_dimensions_are_frozen(self):
        self.assertEqual(len(CASES), 4)
        self.assertEqual(len(SCENES), 4)
        self.assertEqual(len(MODELS), 3)
        self.assertEqual(METRICS, ("gradient", "laplacian", "bandpass"))
        self.assertEqual(STRIDES, (4, 2, 1))
        self.assertEqual(len(FINE_FOCUS_D), 25)
        self.assertEqual(tuple(FINE_FOCUS_D[::4]), tuple(-.75+.25*i for i in range(7)))
        self.assertEqual(tuple(FINE_FOCUS_D[::2]), tuple(-.75+.125*i for i in range(13)))
        self.assertEqual((PEAK_TIE_REL, CURVE_FLAT_REL), (.002, .01))
        self.assertEqual(len({c.name for c in CASES}),4)
        self.assertEqual(CASES[-1].gamma,2.4)

    def test_extra_scenes_are_different_repeatable_and_bounded(self):
        x=make_r8_scene("radial_rings",64)
        y=make_r8_scene("oblique_gratings",64)
        np.testing.assert_array_equal(x,make_r8_scene("radial_rings",64))
        self.assertEqual(x.shape,(64,64))
        self.assertGreater(np.linalg.norm(x-y),1.)
        for z in (x,y):
            self.assertGreaterEqual(z.min(),0.)
            self.assertLessEqual(z.max(),1.)
        with self.assertRaises(ValueError):
            make_r8_scene("unregistered",64)

    def test_hypothetical_spectrum_peak_offsets_are_not_ignored(self):
        a=SpectralCase("reference_test",18.,(0.,0.,0.),2.2)
        b=SpectralCase("shift_test",18.,(8.,-6.,8.),2.2)
        ha=shifted_otfs(a,0.,64)
        hb=shifted_otfs(b,0.,64)
        self.assertEqual(ha.shape,hb.shape)
        self.assertGreater(np.linalg.norm(ha-hb),1e-6)
        self.assertTrue(np.isfinite(hb).all())
        np.testing.assert_allclose(ha[:,0,0],1.,atol=1e-10)
        np.testing.assert_allclose(hb[:,0,0],1.,atol=1e-10)


class SharpnessMetricTests(unittest.TestCase):
    def test_all_focus_measures_are_zero_on_constant_image(self):
        m=focus_metrics(np.full((64,64),.42))
        self.assertEqual(set(m),set(METRICS))
        for value in m.values():
            self.assertAlmostEqual(value,0.,places=12)

    def test_checkerboard_is_laplacian_sensitive(self):
        y,x=np.indices((64,64))
        image=((x+y)%2).astype(float)
        result=focus_metrics(image)
        self.assertGreater(result["laplacian"],1)
        self.assertGreaterEqual(result["gradient"],0)
        self.assertGreaterEqual(result["bandpass"],0)

    def test_smooth_and_sharp_scenes_have_finite_nonnegative_scores(self):
        for name in SCENES:
            m=focus_metrics(make_r8_scene(name,64))
            self.assertTrue(all(np.isfinite(v) and v>=0 for v in m.values()))

    def test_reject_nonfinite_and_wrong_dimensionality(self):
        with self.assertRaises(ValueError):
            focus_metrics(np.ones((3,8,8)))
        with self.assertRaises(ValueError):
            focus_metrics(np.full((8,8),np.nan))


class PeakGateTests(unittest.TestCase):
    def setUp(self):
        self.grid=np.asarray(FINE_FOCUS_D)

    def test_clear_directional_shift_is_resolved(self):
        xx=np.arange(25)
        a=1.+np.exp(-.5*((xx-8)/2)**2)
        b=1.+np.exp(-.5*((xx-16)/2)**2)
        r=describe_peak(a,b,self.grid)
        self.assertEqual(r["minus_status"],"RESOLVED")
        self.assertEqual(r["plus_status"],"RESOLVED")
        self.assertAlmostEqual(r["reportable_delta_peak_D"],.5)
        self.assertAlmostEqual(r["raw_delta_peak_D"],.5)

    def test_tie_and_plateau_abstain(self):
        a=np.ones(25)
        b=np.ones(25)
        r=describe_peak(a,b,self.grid)
        self.assertIsNone(r["reportable_delta_peak_D"])
        self.assertIn("ABSTAIN",r["minus_status"])
        a=1.+.5*np.exp(-.5*((np.arange(25)-9.5)/1.7)**2)
        b=1.+.5*np.exp(-.5*((np.arange(25)-14.5)/1.7)**2)
        r=describe_peak(a,b,self.grid)
        self.assertIsNone(r["reportable_delta_peak_D"])
        self.assertEqual(r["minus_status"],"ABSTAIN_NEAR_TIE")

    def test_boundary_is_always_censored(self):
        y=np.linspace(1,3,25)
        r=describe_peak(y,y,self.grid)
        self.assertEqual(r["minus_status"],"ABSTAIN_BOUNDARY")
        self.assertIsNone(r["reportable_delta_peak_D"])

    def test_negative_and_nan_focus_scores_rejected(self):
        y=np.ones(25)
        with self.assertRaises(ValueError):
            describe_peak(y,np.full(25,np.nan),self.grid)
        with self.assertRaises(ValueError):
            describe_peak(y,-y,self.grid)
        with self.assertRaises(ValueError):
            describe_peak(y,y,self.grid[::-1])


class StudyAndProvenanceTests(unittest.TestCase):
    def test_one_scene_case_full_pipeline_outputs_27_rows(self):
        rows,s=execute(scenes=("original_texture",),cases=(CASES[0],),
                       size=64,maxiter=90)
        self.assertEqual(len(rows),len(MODELS)*len(METRICS)*len(STRIDES))
        self.assertEqual(s["study"],STUDY)
        self.assertEqual(s["rows"],27)
        self.assertTrue(s["all_optimizers_success"])
        self.assertEqual(len(s["fitting_status"]),6)
        self.assertFalse(any("human" in str(r.get("evidence_scope","")).lower()
                             for r in rows))
        self.assertEqual(sum(x["rows"] for x in s["sensitivity_cells"].values()),27)
        for r in rows:
            self.assertIn(r["minus_status"],{
                "ABSTAIN_BOUNDARY","ABSTAIN_FLAT","ABSTAIN_NEAR_TIE","RESOLVED"})
            self.assertTrue(np.isfinite(r["raw_delta_peak_D"]))
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            write_outputs(out,rows,s)
            self.assertEqual(set(x.name for x in out.iterdir()),
                {"sensitivity.csv","summary.json","manifest.json"})
            manifest=json.loads((out/"manifest.json").read_text())
            self.assertFalse(manifest["display_spd_measured"])
            self.assertFalse(manifest["human_accommodation_measured"])
            self.assertEqual(len(manifest["code_sha256"]),6)
            with (out/"sensitivity.csv").open(newline="") as f:
                self.assertEqual(len(list(csv.DictReader(f))),27)

    def test_invalid_scope_rejected(self):
        with self.assertRaises(ValueError):
            execute(scenes=())
        with self.assertRaises(ValueError):
            execute(cases=())
        with self.assertRaises(ValueError):
            execute(size=63)
        with self.assertRaises(ValueError):
            execute(maxiter=0)
        with self.assertRaises(ValueError):
            execute(scenes=("original_texture","original_texture"))


if __name__=="__main__":
    unittest.main()
