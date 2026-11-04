# GazeBloom application architecture — v0.2

Status: working design + initial idle-awareness adapter. Updated 2026-11-04.

## Goals
- A small, accessible, local-first reminder application for monitor users.
- Every recommendation must have a documented evidence status.
- A removable experimental research subsystem, not part of default wellness behavior.
- No measurement of gaze, accommodation, retinal condition or medical outcomes.

## Current modules

```text
Desktop Tk adapter (gazebloom/desktop.py)
  | user actions / visible state
  +--> BreakTimer (engine.py)              pure, monotonic state machine
  +--> IdleWatcher (activity.py)           background worker; bounded OS calls
  |      +--> LinuxIdleProbe               GNOME Mutter D-Bus / X11 xprintidle
  |      +--> IdleGate                     pause/resume ownership policy
  +--> optional LocalEventLog              minimal local JSONL, explicit opt-in
  +--> Linux notify-send (best effort)     event-to-notification adapter

Unrelated research experiments:
  experiments/gaussian_lca_v0, experiments/waveoptics_q1_v1
  research/evidence_catalog.json (intervention eligibility)
```

Dependencies managed by uv. Reminder runtime has no third-party Python dependencies; Tk native system support is still required. Scientific extras are optional.

## Invariants
1. **Monotonic deadlines:** timezone or clock edits cannot create multiple due notifications; no catch-up burst after suspension.
2. **Consent and control:** Start/Stop, pause, snooze, skip and manual break confirmation are always user controlled.
3. **Manual pause wins:** IdleGate only auto-resumes a pause *it* owns. Unknown idle readings cause neither auto-resume nor auto-pause.
4. **Breaks are intentional:** Work countdown may be held when idle, but the 20-second manually initiated break timer is never paused by idle detection.
5. **No false measurements:** Input inactivity is not screen gaze, eye fatigue or true activity. A `break_completed` log means user confirmation, not observed ocular behavior.
6. **No silent collection:** OS idle values are sampled in memory only when explicitly opted-in. No raw key events, mouse positions, screenshots, active-window names, camera feeds or telemetry. Optional event logging remains explicit.
7. **Default remains safe:** When activity detection is unsupported/unavailable, the manual-session timer continues and the GUI displays that its idle status is unknown.

## Platform boundary
- GNOME (X11 or Wayland): Mutter IdleMonitor `GetIdletime` on user's session D-Bus, when exposed.
- X11: optional `xprintidle` utility, if available.
- Other Wayland compositors: **unsupported** in this v0.2 adapter; no unsafe assumption about available APIs.
- Probe runs in a background thread; GUI reads its bounded queue on Tk's main thread. All OS subprocesses have timeouts.
- There is no universal Linux tray implementation. GNOME may require an AppIndicator extension. System-tray packaging is a separate research/engineering gate, not a guaranteed feature.

## Next slices (review before implementing)
1. Versioned settings storage (config version, atomic write, safe defaults) and accessible Persian/English UI.
2. Per-desktop capabilities probe and a manual test matrix: GNOME Wayland / GNOME Xorg / KDE Wayland / unsupported.
3. Tray integration via StatusNotifierItem/AppIndicator where supported, graceful window fallback otherwise.
4. Better suspend/lock/fullscreen semantics, opt-in background startup and robust notification lifecycle.
5. Human-centered low-cost app evaluation focused on adherence and self-reported discomfort, **not** eye accommodation or claims of treatment.

External OS references:
- https://gnome.pages.gitlab.gnome.org/gnome-desktop/html/gnome-desktop3/gnome-desktop3-GnomeIdleMonitor.html
- https://chromium.googlesource.com/chromium/src/+/a19d60431025495bdf6d9c71854f5ddacb3e60cc/ui/ozone/platform/wayland/host/org_gnome_mutter_idle_monitor.cc
- https://manpages.ubuntu.com/manpages/jammy/man1/xprintidle.1.html
- https://extensions.gnome.org/extension/615/appindicator-support/
