"""R14 safety/timing simulations. Tests never render experimental image pixels."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from session import (
    REST_S, STATES, STUDY, VIEW_S, SessionViolation, SimulatedSession,
    validate_binding,
)
from simulate import fake_binding, run_scenarios
from demo_gui import launch


class BindingValidation(unittest.TestCase):
    def setUp(self):
        self.binding=fake_binding()

    def test_valid_four_words_each_once_per_condition(self):
        self.assertIsNone(validate_binding(self.binding))
        self.assertEqual(len(self.binding),8)

    def test_missing_row_and_duplicate_id_rejected(self):
        with self.assertRaises(SessionViolation):
            validate_binding(self.binding[:7])
        x=deepcopy(self.binding)
        x[2]["trial_id"]=x[1]["trial_id"]
        with self.assertRaises(SessionViolation):
            validate_binding(x)

    def test_missing_binding_field_and_path_traversal_rejected(self):
        x=deepcopy(self.binding)
        x[0].pop("image_sha256")
        with self.assertRaises(SessionViolation):
            validate_binding(x)
        x=deepcopy(self.binding)
        x[0]["image_relative_path"]="../session-privacy.png"
        with self.assertRaises(SessionViolation):
            validate_binding(x)

    def test_bad_hash_word_or_image_filename_rejected(self):
        for field,value in (("image_sha256","not-a-sha"),("word","OTHER"),
                            ("image_relative_path","UNAPPROVED_images/03_MIRA_X.png")):
            x=deepcopy(self.binding)
            x[0][field]=value
            with self.subTest(field=field),self.assertRaises(SessionViolation):
                validate_binding(x)

    def test_repetition_not_opposite_arm_rejected(self):
        x=deepcopy(self.binding)
        x[4]["condition_code"]=x[0]["condition_code"]
        x[4]["image_relative_path"]=x[0]["image_relative_path"]
        with self.assertRaises(SessionViolation):
            validate_binding(x)

    def test_limits_not_mutable(self):
        for field,value in (("max_view_seconds","11"),("min_rest_seconds","29")):
            x=deepcopy(self.binding)
            x[0][field]=value
            with self.subTest(field=field),self.assertRaises(SessionViolation):
                validate_binding(x)


class StateMachineTests(unittest.TestCase):
    def setUp(self):
        self.session=SimulatedSession(fake_binding())

    def test_starts_ready_without_visible_image_or_authorization(self):
        s=self.session.snapshot(0.)
        self.assertEqual(s.state,"READY")
        self.assertEqual(s.trial_number,1)
        self.assertFalse(s.stimulus_visible)
        self.assertFalse(s.human_exposure_authorized)
        self.assertTrue(s.stop_available)

    def test_fixed_max_view_and_manual_response(self):
        s=self.session
        s.start(2.)
        self.assertEqual(s.state,"VIEWING")
        self.assertAlmostEqual(s.snapshot(11.9).display_seconds_remaining,.1)
        self.assertEqual(s.state,"VIEWING")
        s.tick(12.)
        self.assertEqual(s.state,"RESPONSE")
        self.assertFalse(s.snapshot(12.).stimulus_visible)
        with self.assertRaises(SessionViolation):
            s.start(12.1)

    def test_early_rating_or_back_to_back_start_rejected(self):
        s=self.session
        with self.assertRaises(SessionViolation):
            s.record_response(0.,clarity=7,comfort=7)
        s.start(1.)
        with self.assertRaises(SessionViolation):
            s.start(1.1)
        with self.assertRaises(SessionViolation):
            s.record_response(2.,clarity=7,comfort=7)
        self.assertEqual(s.rows,[])

    def test_rest_30s_and_explicit_next_start(self):
        s=self.session
        s.start(0.)
        s.tick(10.)
        s.record_response(10.1,clarity=7,comfort=6,reading_correct=True)
        self.assertEqual(s.state,"REST")
        self.assertEqual(s.rows[0]["stopped"],"0")
        s.tick(40.)
        self.assertEqual(s.state,"REST")
        with self.assertRaises(SessionViolation):
            s.start(40.)
        s.tick(40.1)
        self.assertEqual(s.state,"READY")
        self.assertEqual(s.current,1)
        self.assertEqual(len(s.rows),1)
        s.start(40.2)
        self.assertEqual(s.state,"VIEWING")
        self.assertEqual(s.current,1)

    def test_tick_cannot_start_any_trial(self):
        s=self.session
        for t in (0.,20.,1000.):
            s.tick(t)
            self.assertEqual(s.state,"READY")
        self.assertEqual(len(s.event_log),0)

    def test_stop_during_view_is_terminal_and_retains_missingness(self):
        s=self.session
        s.start(0.)
        s.stop(1.)
        r=s.report()
        self.assertEqual(r["terminal_state"],"STOPPED")
        self.assertEqual(r["response_rows"],1)
        self.assertEqual(r["remaining_not_observed_trials"],7)
        self.assertEqual(s.rows[0]["trial_id"],"T01")
        self.assertEqual(s.rows[0]["clarity_0_10"],"")
        self.assertEqual(s.rows[0]["stopped"],"1")
        self.assertFalse(s.snapshot(5).stimulus_visible)
        with self.assertRaises(SessionViolation):
            s.start(6.)
        with self.assertRaises(SessionViolation):
            s.record_response(7.,clarity=7,comfort=7)
        s.tick(1000.)
        self.assertEqual(s.state,"STOPPED")

    def test_stop_from_ready_is_terminal_without_false_trial_row(self):
        s=self.session
        s.stop(0.)
        self.assertEqual(s.state,"STOPPED")
        self.assertEqual(s.rows,[])
        self.assertEqual(s.report()["remaining_not_observed_trials"],8)

    def test_stop_during_response_records_no_scores(self):
        s=self.session
        s.start(0.)
        s.tick(10.)
        s.stop(11.)
        self.assertEqual(s.rows[0]["stopped"],"1")
        self.assertEqual(s.rows[0]["comfort_0_10"],"")

    def test_stop_during_rest_does_not_fake_next_trial(self):
        s=self.session
        s.start(0.)
        s.tick(10.)
        s.record_response(10.1,clarity=5,comfort=5)
        s.stop(12.)
        self.assertEqual(s.report()["response_rows"],1)
        self.assertEqual(s.report()["completed_simulated_trials"],1)
        self.assertEqual(s.report()["stopped_simulated_trials"],0)
        self.assertEqual(s.state,"STOPPED")

    def test_stop_twice_is_idempotent(self):
        s=self.session
        s.start(0.)
        s.stop(1.)
        n=len(s.event_log)
        s.stop(1.1)
        self.assertEqual(len(s.event_log),n)
        self.assertEqual(len(s.rows),1)

    def test_discomfort_always_permanent_stop_even_if_scores_supplied(self):
        s=self.session
        s.start(0.)
        s.tick(10.)
        s.record_response(10.1,clarity=10,comfort=10,
                          reading_correct=True,discomfort=True)
        self.assertEqual(s.state,"STOPPED")
        self.assertEqual(s.rows[0]["discomfort_flag"],"1")
        self.assertEqual(s.rows[0]["stopped"],"1")
        self.assertEqual(s.rows[0]["comfort_0_10"],"")
        s.tick(100.)
        with self.assertRaises(SessionViolation):
            s.start(101.)

    def test_nan_infinity_backwards_clock_and_negative_clock_rejected(self):
        for t in (-1., float("nan"), float("inf")):
            with self.subTest(t=t),self.assertRaises(SessionViolation):
                self.session.tick(t)
        s=self.session
        s.tick(10.)
        with self.assertRaises(SessionViolation):
            s.tick(9.)

    def test_invalid_scores_and_flags_do_not_create_responses(self):
        s=self.session
        s.start(0.)
        s.tick(10.)
        for name,v in (("clarity",11.),("comfort",-1.),
                       ("clarity",float("nan")),("comfort",float("inf"))):
            kw={"clarity":7.,"comfort":7.}
            kw[name]=v
            with self.subTest(name=name,value=v),self.assertRaises(SessionViolation):
                s.record_response(11.,**kw)
        with self.assertRaises(SessionViolation):
            s.record_response(12.,clarity=7,comfort=7,reading_correct="1")
        self.assertEqual(s.rows,[])
        self.assertEqual(s.state,"RESPONSE")

    def test_full_eight_trial_completion_no_auto_start(self):
        s=self.session
        t=0.
        for i in range(8):
            s.start(t)
            s.tick(t+VIEW_S)
            s.record_response(t+VIEW_S+.1,clarity=7,comfort=7,reading_correct=True)
            t+=VIEW_S+.1
            if i<7:
                self.assertEqual(s.state,"REST")
                s.tick(t+REST_S)
                self.assertEqual(s.state,"READY")
                t+=REST_S
        self.assertEqual(s.state,"FINISHED")
        self.assertEqual(len(s.rows),8)
        with self.assertRaises(SessionViolation):
            s.start(t+1)
        r=s.report()
        self.assertEqual(r["completed_simulated_trials"],8)
        self.assertFalse(r["human_exposure_authorized"])
        self.assertFalse(r["participant_data_collected"])
        self.assertFalse(r["stimulus_images_displayed"])

    def test_gui_without_operator_optin_rejected_before_tk(self):
        with self.assertRaisesRegex(ValueError,"--operator-demo"):
            launch(operator_demo=False)

    def test_simulated_time_never_claims_real_latency_safety(self):
        s=self.session
        s.start(0.)
        s.tick(99999.)
        self.assertEqual(s.state,"RESPONSE")
        self.assertFalse(s.snapshot(100000.).stimulus_visible)
        self.assertIn("not verified real-world safety",s.report()["safety_note"])


class CLISimulationTests(unittest.TestCase):
    def test_all_four_scenarios_are_human_free(self):
        d=run_scenarios()
        self.assertTrue(d["all_cases_complete"])
        self.assertEqual(d["study"],STUDY)
        self.assertEqual(d["human_participants"],0)
        self.assertEqual(d["actual_pngs_opened"],0)
        self.assertEqual(d["camera_recordings"],0)
        self.assertEqual(len(d["cases"]),4)
        self.assertEqual(d["cases"]["normal_eight_trials"]["response_rows"],8)
        self.assertEqual(d["cases"]["stop_while_simulated_viewing"]["terminal_state"],"STOPPED")
        self.assertEqual(d["cases"]["discomfort_permanent_stop"]["terminal_state"],"STOPPED")
        self.assertTrue(all(not r["human_exposure_authorized"] for r in d["cases"].values()))

    def test_simulate_cli_writes_once_and_doesnt_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"dry-run.json"
            cmd=[sys.executable,str(Path(__file__).with_name("simulate.py")),
                 "--out",str(path)]
            p=subprocess.run(cmd,capture_output=True,text=True,check=True)
            self.assertFalse(json.loads(p.stdout)["human_exposure_authorized"])
            self.assertEqual(json.loads(path.read_text()),run_scenarios())
            retry=subprocess.run(cmd,capture_output=True,text=True)
            self.assertNotEqual(retry.returncode,0)
            self.assertIn("refuse to replace",retry.stderr)

    def test_operator_demo_cli_without_flag_rejected_without_Tk(self):
        cmd=[sys.executable,str(Path(__file__).with_name("demo_gui.py"))]
        p=subprocess.run(cmd,capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0)
        self.assertIn("--operator-demo",p.stderr)


if __name__=="__main__":
    unittest.main()
