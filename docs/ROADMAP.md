# GazeBloom roadmap — evidence before claims (2026-11-04)

## Track A — practical screen-break app (maintenance only during active Track B research)
- [x] Target use case fixed: screen breaks and low-risk visual-wellness behavior.
- [x] Initial evidence register, explicit confidence boundaries, intervention catalogue and low-cost evaluation proposal.
- [ ] Confirm evaluation design and outcome measures; approve any participant study before starting.
- [x] Monotonic-clock timer, private opt-in local event log and first manual desktop Tkinter UI.
- [x] Build opt-in Linux idle-awareness probe (GNOME D-Bus / X11 xprintidle), conservative hold policy and offline tests.
- [x] Owner reported successful manual idle-aware behavior on Ubuntu (2026-11-04); platform-wide suspend/Wayland matrix remains untested.
- [ ] Broader suspend/wake and other desktop-compositor validation after research milestone.
- [ ] Cross-platform notifications, tray integration, versioned settings, accessible/localized UI and packaging.
- [ ] Test notification state machine, idle detection, pause/snooze, user control, performance and privacy.
- [ ] Conduct small consent-based feasibility pilot (reported symptoms and behaviors, not optics).
- [ ] Review evidence and usability findings before any public efficacy claims.

## Track B — active research priority (isolated from wellness claims)
- [x] Gaussian + LCA images and video exploratory generator.
- [x] Scalar wave-optics PSF simulation and synthetic-data Q2 analysis code.
- [x] R1 numerical-invariant checks, descriptive FFT-grid convergence audit and deterministic model sensitivity runner.
- [x] Execute and inspect full R1 16-case / 32-row pilot, including absolute residuals and a single-case FFT-grid comparison ([review](../experiments/r1_model_sensitivity/RESULTS_REVIEW_FA.md)).
- [ ] Independently validate physical units and PSF sampling accuracy across multiple pupil/defocus scenarios.
- [ ] Build physically constrained, display-aware retinal image optimizer (not just Gaussian per-channel blur).
- [x] R1 pilot design sweeps distance, pixel pitch, pupil size and defocus sign/magnitude.
- [ ] Add measured RGB spectra, calibrated gamma and monitor brightness; these are not covered by R1.
- [ ] Literature-based synthesis; label predicted responses as hypotheses.
- [ ] Actual human accommodation measurement remains **out of scope** without appropriate optical instruments and expert oversight.

## Constraints
- No therapeutic or muscle-strengthening claims.
- Subjective blur, comfort or perceived depth do not validate accommodation response.
- The first working app should not include experimental chromatic stimuli in default break exercises.
- See [evidence review](EVIDENCE_REVIEW_FA.md), [intervention catalog](INTERVENTIONS_V1_FA.md), [MVP spec](MVP_SPEC_FA.md), [proposed study](LOW_COST_EVALUATION_FA.md).
