"""Offline opt-in idle-awareness tests; no desktop, GUI or human gaze needed."""
from __future__ import annotations

import subprocess
import threading
import unittest
from types import SimpleNamespace

from gazebloom import BreakTimer, Settings, State
from gazebloom.activity import (
    IdleGate, IdleReading, IdleWatcher, LinuxIdleProbe, parse_idle_milliseconds,
)


class ParsingTests(unittest.TestCase):
    def test_gdbus_and_x11(self):
        for raw, expected in (
            ("(uint64 4500,)\n", 4500),
            ("(4500,)\n", 4500),
            ("4500\n", 4500),
            ("0", 0),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(parse_idle_milliseconds(raw), expected)

    def test_untrustworthy_output_is_unknown(self):
        for raw in ("", "idle 17", "-5", "inf", "(uint64 -3,)", "123ms",
                    "(notanumber,)", "99999999999999999999999"):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_idle_milliseconds(raw))


class ProbeTests(unittest.TestCase):
    def test_gnome_wayland_getidletime(self):
        commands = []

        def runner(argv, **kwargs):
            commands.append((argv, kwargs))
            return SimpleNamespace(returncode=0, stdout="(uint64 78000,)\n")

        probe = LinuxIdleProbe(
            environ={"XDG_CURRENT_DESKTOP": "ubuntu:GNOME", "XDG_SESSION_TYPE": "wayland"},
            which=lambda cmd: "/usr/bin/" + cmd if cmd == "gdbus" else None,
            runner=runner,
        )
        idle, backend = probe.read()
        self.assertEqual((idle, backend), (78.0, "gnome-mutter"))
        self.assertEqual(commands[0][0][-1], "org.gnome.Mutter.IdleMonitor.GetIdletime")
        self.assertLessEqual(commands[0][1]["timeout"], 1)

    def test_x11_fallback_and_no_shell(self):
        commands = []

        def runner(argv, **kwargs):
            commands.append(argv)
            return SimpleNamespace(returncode=0, stdout="60000\n")

        probe = LinuxIdleProbe(
            environ={"XDG_CURRENT_DESKTOP": "xfce", "XDG_SESSION_TYPE": "x11"},
            which=lambda cmd: cmd if cmd == "xprintidle" else None,
            runner=runner,
        )
        self.assertEqual(probe.read(), (60.0, "x11-xprintidle"))
        self.assertEqual(commands, [["xprintidle"]])

    def test_gnome_x11_falls_back_after_dbus_failure(self):
        def runner(argv, **kwargs):
            if argv[0] == "gdbus":
                raise subprocess.TimeoutExpired(argv, 0.75)
            return SimpleNamespace(returncode=0, stdout="2500\n")
        probe = LinuxIdleProbe(
            environ={"XDG_CURRENT_DESKTOP": "GNOME", "XDG_SESSION_TYPE": "x11"},
            which=lambda c: c, runner=runner,
        )
        self.assertEqual(probe.read(), (2.5, "x11-xprintidle"))

    def test_non_gnome_wayland_does_not_query_x11(self):
        calls = []
        def runner(argv, **kwargs):
            calls.append(argv)
            raise AssertionError("no commands should run")
        probe = LinuxIdleProbe(
            environ={"XDG_CURRENT_DESKTOP": "KDE", "XDG_SESSION_TYPE": "wayland"},
            which=lambda c: c, runner=runner,
        )
        self.assertEqual(probe.read(), (None, "unavailable"))
        self.assertEqual(calls, [])

    def test_failed_command_is_unknown(self):
        probe = LinuxIdleProbe(
            environ={"XDG_CURRENT_DESKTOP": "GNOME", "XDG_SESSION_TYPE": "wayland"},
            which=lambda c: c,
            runner=lambda argv, **kw: SimpleNamespace(returncode=1, stdout=""),
        )
        self.assertEqual(probe.read(), (None, "unavailable"))


class GateTests(unittest.TestCase):
    def setUp(self):
        self.engine = BreakTimer(Settings(interval_seconds=100, break_seconds=20))
        self.gate = IdleGate(threshold_seconds=60)

    def test_default_is_off_outside_gate(self):
        self.engine.start(0)
        self.engine.advance(100)
        self.assertEqual(self.engine.state, State.PROMPT)

    def test_away_pauses_and_activity_resumes_countdown(self):
        self.engine.start(0)
        self.gate.observe(70, 30, self.engine)
        self.assertTrue(self.gate.auto_paused)
        self.assertEqual(self.engine.state, State.PAUSED)
        self.assertEqual(self.engine.remaining_seconds(1000), 70)
        self.engine.advance(1000)
        self.assertEqual(self.engine.state, State.PAUSED)
        self.gate.observe(0.2, 1500, self.engine)
        self.assertEqual(self.engine.state, State.WORKING)
        self.engine.advance(1569.99)
        self.assertEqual(self.engine.state, State.WORKING)
        self.engine.advance(1570)
        self.assertEqual(self.engine.state, State.PROMPT)
        sources = [e["source"] for e in self.engine.take_events()
                   if e["event_type"] in ("paused", "resumed")]
        self.assertEqual(sources, ["idle_monitor", "idle_monitor"])

    def test_manual_pause_never_auto_resumes(self):
        self.engine.start(0)
        self.engine.pause(10)
        self.gate.observe(0, 40, self.engine)
        self.assertEqual(self.engine.state, State.PAUSED)
        self.assertFalse(self.gate.auto_paused)

    def test_unknown_never_resumes_an_automatic_pause(self):
        self.engine.start(0)
        self.gate.observe(100, 10, self.engine)
        self.gate.observe(None, 20, self.engine)
        self.assertEqual(self.engine.state, State.PAUSED)
        self.assertTrue(self.gate.auto_paused)
        self.gate.observe(2, 30, self.engine)
        self.assertEqual(self.engine.state, State.WORKING)

    def test_idle_during_break_does_not_interrupt_user_break(self):
        self.engine.start(0)
        self.engine.begin_break(10)
        self.gate.observe(80, 20, self.engine)
        self.assertEqual(self.engine.state, State.BREAK)
        self.engine.advance(30)
        self.assertEqual(self.engine.state, State.BREAK_READY)
        self.assertFalse(self.gate.auto_paused)

    def test_pending_prompt_deferred_until_active(self):
        self.engine.start(0)
        self.engine.advance(100)
        self.gate.observe(120, 101, self.engine)
        self.assertEqual(self.engine.state, State.PAUSED)
        self.gate.observe(0.1, 500, self.engine)
        self.assertEqual(self.engine.state, State.PROMPT)

    def test_manual_override_cancels_auto_ownership(self):
        self.engine.start(0)
        self.gate.observe(100, 10, self.engine)
        self.gate.manual_override()
        self.gate.observe(0, 20, self.engine)
        self.assertEqual(self.engine.state, State.PAUSED)
        self.assertFalse(self.gate.auto_paused)

    def test_invalid_threshold_and_unknown_reading(self):
        for bad in (0, 14, 3601, float("nan")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                IdleGate(threshold_seconds=bad)
        self.engine.start(0)
        self.gate.observe(float("nan"), 1, self.engine)
        self.assertEqual(self.gate.status, "unknown")
        self.assertEqual(self.engine.state, State.WORKING)


class WatcherTests(unittest.TestCase):
    def test_background_poll_latest_and_stop(self):
        called = threading.Event()

        class DummyProbe:
            def read(self):
                called.set()
                return 5.0, "mock"

        watcher = IdleWatcher(DummyProbe(), poll_seconds=1.0)
        watcher.start()
        try:
            self.assertTrue(called.wait(timeout=2.0))
            found = None
            for _ in range(100):
                found = watcher.latest()
                if found is not None:
                    break
                # Allow worker to enqueue without depending on a sleep-heavy test.
                called.wait(0.01)
            self.assertIsNotNone(found)
            self.assertEqual((found.idle_seconds, found.backend), (5.0, "mock"))
        finally:
            watcher.stop()

    def test_invalid_poll_rate(self):
        with self.assertRaises(ValueError):
            IdleWatcher(LinuxIdleProbe(), poll_seconds=0)


if __name__ == "__main__":
    unittest.main()
