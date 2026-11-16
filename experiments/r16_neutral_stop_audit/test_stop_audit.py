"""R16 no-human STOP dispatch tests: no real PNGs, no Tk or display needed."""
from __future__ import annotations

import math
import unittest

from stop_audit import STUDY, StopLatch, StopResult, summary


class StopAuditTests(unittest.TestCase):
    def test_stop_is_irreversible_and_idempotent(self):
        calls = []
        ticks = iter((1.0, 1.002))
        gate = StopLatch(lambda: calls.append("blank"), lambda: next(ticks))
        gate.start_placeholder()
        result = gate.stop("button")
        self.assertEqual(result.state, "STOPPED")
        self.assertEqual(result.source, "button")
        self.assertAlmostEqual(result.dispatch_ms, 2.0)
        self.assertEqual(gate.stop("escape"), result)
        self.assertEqual(calls, ["blank"])
        with self.assertRaises(ValueError):
            gate.start_placeholder()

    def test_stop_from_ready_and_close(self):
        count = []
        gate = StopLatch(lambda: count.append(1), lambda: 10.0)
        self.assertEqual(gate.stop("close").state, "STOPPED")
        self.assertEqual(len(count), 1)

    def test_neutralization_failure_is_terminal_not_successful(self):
        attempts = []
        def failed():
            attempts.append(1)
            raise RuntimeError("failed to neutralize")
        gate = StopLatch(failed, lambda: 3.0)
        gate.start_placeholder()
        with self.assertRaises(RuntimeError):
            gate.stop("button")
        self.assertEqual(gate.state, "STOPPED")
        self.assertFalse(gate.stop("escape").neutralize_callback_succeeded)
        self.assertIsNone(gate.last_result.dispatch_ms)
        self.assertEqual(len(attempts), 1)
        with self.assertRaises(ValueError):
            gate.start_placeholder()

    def test_invalid_source_does_not_mutate(self):
        gate = StopLatch(lambda: None)
        with self.assertRaises(ValueError):
            gate.stop("untrusted")
        self.assertEqual(gate.state, "READY")

    def test_clock_failure_is_terminal(self):
        for clock in (lambda: math.nan, lambda: -1.0):
            gate = StopLatch(lambda: None, clock)
            with self.assertRaises(ValueError):
                gate.stop("synthetic")
            self.assertEqual(gate.state, "STOPPED")
            self.assertFalse(gate.stop("synthetic").neutralize_callback_succeeded)

    def test_negative_elapsed_is_failure_not_valid_measurement(self):
        ticks = iter((9.0, 8.0))
        gate = StopLatch(lambda: None, lambda: next(ticks))
        with self.assertRaises(ValueError):
            gate.stop("synthetic")
        self.assertEqual(gate.state, "STOPPED")
        self.assertIsNone(gate.stop("synthetic").dispatch_ms)

    def test_summary_disclaims_display_and_human_evidence(self):
        report = summary([StopResult("STOPPED", "synthetic", 1., True),
                          StopResult("STOPPED", "synthetic", 2., True),
                          StopResult("STOPPED", "synthetic", 3., True)],
                         environment="CI_TK_SYNTHETIC_CALLBACK")
        self.assertEqual(report["study"], STUDY)
        self.assertEqual(report["dispatch_ms_median"], 2.0)
        self.assertFalse(report["human_exposure_authorized"])
        self.assertFalse(report["h1_runner_available"])
        self.assertFalse(report["threshold_certification"])
        self.assertIn("physical_pixel_suppression", report["NOT_measured"])
        self.assertEqual(report["actual_pngs_opened"], 0)

    def test_bad_or_empty_summary_rejected(self):
        with self.assertRaises(ValueError):
            summary([], environment="CI")
        for measurement in (None, float("nan"), -1):
            with self.subTest(measurement=measurement), self.assertRaises(ValueError):
                summary([StopResult("STOPPED", "synthetic", measurement, True)],
                        environment="CI")
        with self.assertRaises(ValueError):
            summary([StopResult("STOPPED", "button", None, False)], environment="CI")


if __name__ == "__main__":
    unittest.main()
