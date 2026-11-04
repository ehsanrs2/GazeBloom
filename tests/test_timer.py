"""Offline deterministic reminder tests; no medical inference."""
import unittest
from gazebloom import BreakTimer, Settings, State, TransitionError

class TimerTests(unittest.TestCase):
    def setUp(self):
        self.t = BreakTimer(Settings(interval_seconds=1200, break_seconds=20, snooze_seconds=300))

    def due(self):
        self.t.start(0); self.t.advance(1200)
        self.assertEqual(self.t.state, State.PROMPT)

    def test_start_and_deadline(self):
        self.t.start(10); self.t.advance(1209)
        self.assertEqual(self.t.state, State.WORKING)
        self.t.advance(1210); self.assertEqual(self.t.state, State.PROMPT)

    def test_reminder_delivered_once(self):
        self.due(); self.t.delivered(1200); self.t.delivered(1201); self.t.advance(2000)
        names = [x["event_type"] for x in self.t.take_events()]
        self.assertEqual(names.count("reminder_due"), 1)
        self.assertEqual(names.count("reminder_delivered"), 1)

    def test_snooze(self):
        self.due(); self.t.snooze(1210); self.t.advance(1509)
        self.assertEqual(self.t.state, State.WORKING)
        self.t.advance(1510); self.assertEqual(self.t.state, State.PROMPT)

    def test_skip(self):
        self.due(); self.t.skip(1201); self.t.advance(2400)
        self.assertEqual(self.t.state, State.WORKING)
        self.t.advance(2401); self.assertEqual(self.t.state, State.PROMPT)

    def test_break_requires_user_confirmation(self):
        self.due(); self.t.begin_break(1205); self.t.advance(1225)
        self.assertEqual(self.t.state, State.BREAK_READY)
        self.assertNotIn("break_completed", [e["event_type"] for e in self.t.take_events()])
        self.t.complete_break(1226)
        self.assertEqual(self.t.take_events()[-1]["source"], "user_confirmed")

    def test_cannot_complete_early(self):
        self.t.start(0); self.t.begin_break(5)
        with self.assertRaises(TransitionError): self.t.complete_break(15)

    def test_interrupted_break_never_completed(self):
        self.t.start(0); self.t.begin_break(5); self.t.interrupt_break(7)
        self.assertNotIn("break_completed", [e["event_type"] for e in self.t.take_events()])

    def test_pause_preserves_countdown(self):
        self.t.start(0); self.t.pause(250); self.t.advance(9000)
        self.assertEqual(self.t.state, State.PAUSED)
        self.t.resume(10000); self.t.advance(10949)
        self.assertEqual(self.t.state, State.WORKING)
        self.t.advance(10950); self.assertEqual(self.t.state, State.PROMPT)

    def test_pause_prompt_no_duplicate_due(self):
        self.due(); self.t.pause(1201); self.t.resume(1300); self.t.advance(50000)
        self.assertEqual([e["event_type"] for e in self.t.take_events()].count("reminder_due"), 1)

    def test_pause_break(self):
        self.t.start(0); self.t.begin_break(100); self.t.pause(108)
        self.t.resume(1000); self.t.advance(1011)
        self.assertEqual(self.t.state, State.BREAK)
        self.t.advance(1012); self.assertEqual(self.t.state, State.BREAK_READY)

    def test_clock_gap_does_not_catch_up(self):
        self.t.start(0); self.t.clock_gap(1100); self.t.advance(5000)
        self.assertEqual(self.t.state, State.PAUSED)
        self.t.resume(6000); self.t.advance(6100)
        self.assertEqual(self.t.state, State.PROMPT)

    def test_stop_idempotent(self):
        self.t.start(0); self.t.stop(5); self.t.stop(10)
        self.assertEqual([e["event_type"] for e in self.t.take_events()].count("session_ended"), 1)

    def test_invalid_actions(self):
        with self.assertRaises(TransitionError): self.t.pause(0)
        with self.assertRaises(TransitionError): self.t.snooze(0)
        self.t.start(0)
        with self.assertRaises(TransitionError): self.t.start(1)
        with self.assertRaises(TransitionError): self.t.delivered(1)

    def test_invalid_clock_and_configuration(self):
        with self.assertRaises(ValueError): Settings(interval_seconds=0)
        with self.assertRaises(ValueError): Settings(interval_seconds=float("nan"))
        self.t.start(100)
        with self.assertRaises(ValueError): self.t.advance(99)
        with self.assertRaises(ValueError): self.t.advance(float("inf"))

if __name__ == "__main__":
    unittest.main()
