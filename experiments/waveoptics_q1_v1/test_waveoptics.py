"""Offline tests of numerical consistency, not physiological validation."""
import unittest
import numpy as np
from waveoptics_validation import (lca_diopters, model_psf, convolve_gaussian_psf,
                                   optimize_one, optimize_control, error_metric, WAVELENGTH_NM)

class WaveOpticsConsistencyTests(unittest.TestCase):
    def test_lca_reference(self):
        self.assertAlmostEqual(lca_diopters(520.),0,delta=.002)
    def test_chromatic_sign(self):
        self.assertGreater(lca_diopters(617),0.)
        self.assertLess(lca_diopters(449),0.)
    def test_psf_normalized(self):
        p=model_psf(.5,520.)
        self.assertEqual(p.shape,(49,49))
        self.assertTrue(np.isfinite(p).all())
        self.assertGreaterEqual(p.min(),0.)
        self.assertAlmostEqual(p.sum(),1.,places=10)
    def test_psf_centrosymmetric(self):
        p=model_psf(.5,520.)
        self.assertLess(np.max(np.abs(p-p[::-1,::-1])),1e-6)
    def test_pupil_changes_psf(self):
        self.assertGreater(error_metric(model_psf(.45,520.,pupil_mm=3.),
                                        model_psf(.45,520.,pupil_mm=5.)),.01)
    def test_zero_gaussian_identity(self):
        a=model_psf(.3,520.)
        self.assertTrue(np.array_equal(a,convolve_gaussian_psf(a,0.)))
    def test_blur_energy_conservation(self):
        a=model_psf(.3,520.)
        self.assertAlmostEqual(convolve_gaussian_psf(a,1.5).sum(),1.,places=10)
    def test_optimization_single_no_worse_than_zero_blur(self):
        b=model_psf(.5,617.)
        t=model_psf(1.,617.)
        sigma=optimize_one(b,t)
        self.assertLessEqual(error_metric(convolve_gaussian_psf(b,sigma),t),
                             error_metric(b,t)+1e-5)
    def test_green_near_far_symmetry(self):
        b=model_psf(0,520.)
        near=model_psf(.45,520.)
        far=model_psf(-.45,520.)
        self.assertLess(error_metric(near,far),.0001)
    def test_control_error_nonnegative(self):
        baseline={c:model_psf(lca_diopters(w),w) for c,w in WAVELENGTH_NM.items()}
        target={c:model_psf(lca_diopters(w)+.45,w) for c,w in WAVELENGTH_NM.items()}
        sigma=optimize_control(baseline,target)
        self.assertTrue(0<=sigma<=10)

if __name__=='__main__':
    unittest.main(verbosity=2)
