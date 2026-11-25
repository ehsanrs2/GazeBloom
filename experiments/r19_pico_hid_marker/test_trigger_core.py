import unittest
from trigger_core import Trigger


class TriggerTests(unittest.TestCase):
    def setup_gate(self):
        events = []
        g = Trigger(lambda: events.append("marker"), lambda: events.append("escape"))
        return g, events

    def ready(self, g):
        self.assertEqual(g.update(False, 0), "WAIT_RELEASE")
        self.assertEqual(g.update(False, .21), "READY")

    def test_held_at_boot_never_fires(self):
        g, events = self.setup_gate()
        for t in (0, .5, 1, 10):
            self.assertEqual(g.update(True, t), "WAIT_RELEASE")
        self.assertEqual(events, [])

    def test_release_then_one_debounced_press_marker_first(self):
        g, events = self.setup_gate()
        self.ready(g)
        self.assertEqual(g.update(True, .3), "READY")
        self.assertEqual(g.update(True, .34), "FIRED")
        self.assertEqual(events, ["marker", "escape"])
        for t, pressed in ((.4, True), (.5, False), (1, True), (2, True)):
            self.assertEqual(g.update(pressed, t), "FIRED")
        self.assertEqual(events, ["marker", "escape"])

    def test_bounce_resets_press_timer(self):
        g, events = self.setup_gate()
        self.ready(g)
        g.update(True, .3)
        g.update(False, .31)
        g.update(True, .32)
        self.assertEqual(g.update(True, .34), "READY")
        self.assertEqual(events, [])
        self.assertEqual(g.update(True, .36), "FIRED")

    def test_marker_error_no_key_and_terminal(self):
        events = []
        def broken():
            raise OSError("marker")
        g = Trigger(broken, lambda: events.append("escape"))
        self.ready(g)
        g.update(True, .3)
        with self.assertRaises(OSError):
            g.update(True, .34)
        self.assertEqual(g.update(True, 1), "FAULT")
        self.assertEqual(events, [])

    def test_hid_error_never_retries(self):
        events = []
        def broken():
            events.append("attempt")
            raise OSError("USB")
        g = Trigger(lambda: events.append("marker"), broken)
        self.ready(g)
        g.update(True, .3)
        with self.assertRaises(OSError):
            g.update(True, .34)
        self.assertEqual(g.update(True, 1), "FAULT")
        self.assertEqual(events, ["marker", "attempt"])

    def test_invalid_clock_fails_closed(self):
        g, events = self.setup_gate()
        self.ready(g)
        with self.assertRaises(ValueError):
            g.update(True, .1)
        self.assertEqual(g.update(True, 1), "FAULT")
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
