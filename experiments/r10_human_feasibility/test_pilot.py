"""R10: privacy, safety-boundary and offline data-integrity invariants."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pilot import (CAMERA_FIELDS, PLAN_FIELDS, RESPONSE_FIELDS, SEQ,
                   analyze_camera_annotations, analyze_responses,
                   make_plan, _read_csv, _write_csv)


class PlanTests(unittest.TestCase):
    def test_balanced_reproducible_counterbalanced_without_stimuli(self):
        x, manifest=make_plan("P001","private-fixed-salt")
        y, other=make_plan("P001","private-fixed-salt")
        self.assertEqual(x,y)
        self.assertEqual(manifest,other)
        self.assertEqual(len(x),8)
        self.assertEqual({x["condition_code"] for x in x},{"X","Y"})
        self.assertEqual([x["trial_id"] for x in x],
                         [f"T{i:02d}" for i in range(1,9)])
        self.assertEqual(sum(t["condition_code"]=="X" for t in x),4)
        self.assertEqual(sum(t["condition_code"]=="Y" for t in x),4)
        self.assertTrue(
            [x["condition_code"] for x in x] in
            [list(SEQ),["Y" if x=="X" else "X" for x in SEQ]])
        self.assertTrue(all(x["max_view_seconds"]=="10" for x in x))
        self.assertTrue(all(x["min_rest_seconds"]=="30" for x in x))
        self.assertFalse(manifest["human_test_authorized_by_script"])
        self.assertFalse(manifest["research_stimuli_included"])
        self.assertFalse(manifest["camera_required"])

    def test_requires_nonidentifying_code_and_nontrivial_salt(self):
        for code,seed in [("real-name","private-fixed-salt"),("P01","private-fixed-salt"),
                          ("P001","short")]:
            with self.subTest(code=code,seed=seed),self.assertRaises(ValueError):
                make_plan(code,seed)

    def test_plan_files_dont_generate_observed_human_results(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/"private"
            script=Path(__file__).with_name("pilot.py")
            p=subprocess.run([sys.executable,str(script),"plan",
                              "--participant-code","P002","--seed","private-fixed-salt",
                              "--out",str(out)],
                             capture_output=True,text=True,check=True)
            self.assertFalse(json.loads(p.stdout)["human_test_authorized_by_script"])
            self.assertEqual({x.name for x in out.iterdir()},
                             {"trials.csv","responses_TEMPLATE.csv","manifest.json"})
            plan=_read_csv(out/"trials.csv",PLAN_FIELDS)
            responses=_read_csv(out/"responses_TEMPLATE.csv",RESPONSE_FIELDS)
            self.assertEqual(len(plan),8)
            self.assertTrue(all(x["clarity_0_10"]=="" for x in responses))
            self.assertTrue(all(x["stopped"]=="" for x in responses))
            second=subprocess.run(
                [sys.executable,str(script),"plan","--participant-code","P002",
                 "--seed","private-fixed-salt","--out",str(out)],
                capture_output=True,text=True)
            self.assertNotEqual(second.returncode,0)
            self.assertIn("must be empty",second.stderr)


class ResponseTests(unittest.TestCase):
    def setUp(self):
        self.plan,_=make_plan("P020","private-fixed-salt")

    def response(self,trial_id,clarity="7",comfort="6",reading="1",
                 discomfort="0",stopped="0"):
        return {"trial_id":trial_id,"clarity_0_10":clarity,
                "comfort_0_10":comfort,"reading_correct":reading,
                "discomfort_flag":discomfort,"stopped":stopped}

    def test_real_entries_are_summarized_without_diopters_or_p_values(self):
        rows=[self.response(t["trial_id"]) for t in self.plan]
        result=analyze_responses(self.plan,rows)
        self.assertEqual(result["rows_submitted"],8)
        self.assertEqual(result["not_submitted_trials"],0)
        self.assertEqual(result["condition_summary"]["X"]["completed_n"],4)
        self.assertEqual(result["condition_summary"]["Y"]["completed_n"],4)
        self.assertEqual(result["condition_summary"]["X"]["mean_clarity_0_10"],7.)
        self.assertEqual(result["condition_summary"]["Y"]["reading_correct_fraction"],1.)
        self.assertIsNone(result["human_accommodation_diopters"])
        self.assertIsNone(result["inferential_p_value"])
        self.assertIsNone(result["clinical_efficacy_or_diagnosis"])

    def test_stopped_trial_kept_as_stopped_and_discomfort(self):
        r=analyze_responses(self.plan,[self.response("T01",clarity="",comfort="",
                        reading="",discomfort="1",stopped="1")])
        self.assertEqual(r["stopped_trials"],1)
        self.assertEqual(r["discomfort_flags"],1)
        self.assertEqual(r["rows_submitted"],1)
        self.assertEqual(r["not_submitted_trials"],7)
        self.assertEqual(sum(x["completed_n"] for x in r["condition_summary"].values()),0)

    def test_no_data_means_no_observed_outcomes(self):
        s=analyze_responses(self.plan,[])
        self.assertEqual(s["rows_submitted"],0)
        self.assertTrue(all(x["mean_comfort_0_10"] is None
                            for x in s["condition_summary"].values()))
        self.assertIsNone(s["human_accommodation_diopters"])

    def test_duplicate_or_nonexistent_trials_rejected(self):
        with self.assertRaises(ValueError):
            analyze_responses(self.plan,[self.response("T01"),self.response("T01")])
        with self.assertRaises(ValueError):
            analyze_responses(self.plan,[self.response("T09")])

    def test_invalid_scores_and_incomplete_completed_trials_rejected(self):
        for v in ("11","-1","nan","inf","bad",""):
            with self.subTest(value=v),self.assertRaises(ValueError):
                analyze_responses(self.plan,[self.response("T01",comfort=v)])
        with self.assertRaises(ValueError):
            analyze_responses(self.plan,[self.response("T01",stopped="YES")])

    def test_optional_reading_metric_can_be_absent(self):
        result=analyze_responses(self.plan,[self.response("T01",reading="")])
        arm=self.plan[0]["condition_code"]
        self.assertIsNone(result["condition_summary"][arm]["reading_correct_fraction"])

    def test_csv_schema_rejects_names_and_email_columns(self):
        with tempfile.TemporaryDirectory() as td:
            x=Path(td)/"s.csv"
            x.write_text("trial_id,email,comfort_0_10\nT01,a@b.co,3\n")
            with self.assertRaises(ValueError):
                _read_csv(x,RESPONSE_FIELDS)


class PhoneAnnotationTests(unittest.TestCase):
    def row(self,t,*,blink="0",face="1",light="1",pupil="5",iris="10"):
        return {"time_s":str(t),"face_visible":face,
                "lighting_stable":light,"blink_event":blink,
                "pupil_px":pupil,"iris_px":iris}

    def test_good_manual_annotation_has_only_behavioral_proxies(self):
        frames=[self.row(i*.2,blink="1" if i in (10,20) else "0")
                for i in range(31)]
        result=analyze_camera_annotations(frames)
        self.assertEqual(result["frames_annotated"],31)
        self.assertEqual(result["quality_frames"],31)
        self.assertEqual(result["blink_events_in_valid_contiguous_segments"],2)
        self.assertAlmostEqual(result["approx_valid_video_seconds"],6.)
        self.assertAlmostEqual(result["blink_per_valid_minute_proxy"],20.)
        self.assertAlmostEqual(result["pupil_iris_ratio_mean_proxy"],.5)
        self.assertIsNone(result["accommodation_diopters"])
        self.assertIsNone(result["absolute_pupil_mm"])
        self.assertFalse(result["photo_or_video_captured_by_script"])

    def test_insufficient_video_returns_unmeasured_blink_rate(self):
        r=analyze_camera_annotations([self.row(0),self.row(1)])
        self.assertIsNone(r["blink_per_valid_minute_proxy"])
        self.assertEqual(r["approx_valid_video_seconds"],0.)

    def test_lost_lighting_or_face_disqualifies_annotation(self):
        with self.assertRaises(ValueError):
            analyze_camera_annotations([self.row(0,blink="1",face="0")])
        with self.assertRaises(ValueError):
            analyze_camera_annotations([self.row(0,blink="1",light="0")])
        with self.assertRaises(ValueError):
            analyze_camera_annotations([self.row(0,pupil="5",iris="")])

    def test_bad_timestamps_rejected(self):
        with self.assertRaises(ValueError):
            analyze_camera_annotations([self.row(0),self.row(0)])
        with self.assertRaises(ValueError):
            analyze_camera_annotations([self.row(0),self.row(-1)])
        with self.assertRaises(ValueError):
            analyze_camera_annotations([self.row(0),self.row(float("nan"))])

    def test_bad_pupil_ratio_rejected(self):
        with self.assertRaises(ValueError):
            analyze_camera_annotations([self.row(0,pupil="12",iris="10")])
        with self.assertRaises(ValueError):
            analyze_camera_annotations([self.row(0,pupil="-1",iris="10")])
        with self.assertRaises(ValueError):
            analyze_camera_annotations([self.row(0,pupil="5",iris="inf")])

    def test_no_camera_rows_returns_no_camera_measurements(self):
        r=analyze_camera_annotations([])
        self.assertEqual(r["frames_annotated"],0)
        self.assertIsNone(r["blink_per_valid_minute_proxy"])
        self.assertIsNone(r["pupil_iris_ratio_mean_proxy"])

    def test_csv_annotations_offline_and_no_video(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"manual_annotations.csv"
            out=Path(td)/"summary.json"
            _write_csv(path,CAMERA_FIELDS,
                [self.row(i*.2,blink="1" if i==10 else "0") for i in range(31)])
            script=Path(__file__).with_name("pilot.py")
            call=subprocess.run([sys.executable,str(script),"camera",
                                 "--annotations",str(path),"--out",str(out)],
                                capture_output=True,text=True,check=True)
            result=json.loads(out.read_text())
            self.assertEqual(result,json.loads(call.stdout))
            self.assertNotIn("face_identity",json.dumps(result))
            self.assertIsNone(result["accommodation_diopters"])


if __name__=="__main__":
    unittest.main()
