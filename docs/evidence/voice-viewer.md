# Voice viewer parity acceptance — 2026-09-10

Implementation scope: [#24](https://github.com/getstud/stud/issues/24), existing UI parity. The [tool inventory](../voice-viewer.md) records the contracts and boundaries. New comparison tabs belong to #19, new estimate features to #20, and saved views/sections/print selections to #26. Comments are excluded.

## Automated validation

- The integrated Python discovery run passed 214 tests, then stopped in the worker-cancellation test with a Python stderr/object dump and exit 120. The cancellation test passed on rerun. The complete 18-test session module and the remaining 21 tests passed in separate runs, covering all 253 Python tests. The original interruption’s root cause is unverified.
- All 120 JavaScript tests passed, including schema/registration, queue/activity lifecycle, guided playback, camera restoration, comparison cancellation, price concurrency, stale context guards and completed writes surviving refresh failures.
- `node --check web/app.js` and `git diff --check` passed.
- A separate code-review agent reviewed the parity changes; its actionable findings were fixed and regression-tested.

## Actual WebMCP browser run

The Codex in-app browser called the registered WebMCP descriptors against isolated projects created by `scripts/native-viewer-fixture.py`. Application actions were invoked through WebMCP; accessibility text, screenshots and a browser-side observer verified their visible results. Fixture prices are synthetic, not market quotes.

| Representative conversation request | Observed result |
| --- | --- |
| Hide the top and shelf; isolate this rail; explode; reset | 10 visible parts, then 1 isolated part, exploded state true, then all 12 restored |
| Which upper rail? | Four exact candidate IDs highlighted for clarification |
| How long is this rail and how high is it mounted? | Current upper front rail: 81-inch finished cut, 31.75-inch mounting height; historical rail: 69 inches |
| Show the front assembly drawing at this mounting level | Drawing/filter context and rendered dimensions agreed; hidden selection was revealed through the shared UI operation |
| Move inside; stop; go back | Interior pose and stop returned camera state; back restored the prior camera exactly |
| What does this design cost, and how much lumber do I need? | $132.00 complete synthetic estimate; six 96-inch 2×4 boards, including purchase specification and allocation evidence |
| Change the board price to $8; use eight boards; clear that quantity | Total became $123.00, quantity became eight, and reset restored the calculated six |
| Remove the manual price | Complete total became null with missing-price evidence; restoring $9.50 restored the fixture price |
| Show the older design while I keep editing the current option | Historical geometry and original estimate appeared. Full camera JSON, including orthographic frustum, matched exactly; the active editing request ID did not change |
| Compare these checkpoints and select the changed rail | Nine changed parts; both panes moved to the same requested camera/zoom; selected inspector reported A: 69 × 1.5 × 3.5 inches, B: 81 × 1.5 × 3.5 inches; editing request unchanged |
| Show the width check | 31/31 checks evaluated with complete coverage; the top highlighted and the detail read “Length: measured 84 in; expected 84.” |
| Send the saved design’s plans and cut list | Final fixture packet `plans_487f12e11f73963f1d5dc95e22b71f93`: complete, checkpoint `784baed7cad4b6394d6914f7c9905b8626e7eca8`, PDF 4 pages / 14,783 bytes, 12 part rows, plus materials CSV, manifest and SVG files |
| Select an unknown part | Structured `PART_NOT_FOUND` error and activity returned to idle |

The final plan-generation activity lasted 38.9 seconds and ended only after the job completed. The browser tool transport timed out while waiting for that long call; `plans.list` recovered the completed packet without regenerating it. A previous packet also completed and its PDF/CSV were parsed locally.

The activity observer recorded `stud-control-glow` while operations ran and `none` when they ended. Reduced-motion emulation recorded active=true with animation=none, followed by active=false. An invalid part and an intentionally encountered recorded-runtime mismatch both released the glow. Read-only context/estimate/measurement calls did not start it. Reduced-motion emulation and observation were removed after verification.

Changing server Python during development changes the recorded engine fingerprint. A packet requested from the earlier fixture correctly rejected native queries for that changed runtime; the fixture was regenerated against the final server code, and the final packet above completed.

## Remaining acceptance limits

Follow-up: the docked inspector was replaced at the user's request by a compact floating inspector. It starts in the least obstructed corner, supports pointer dragging and arrow-key movement, remembers the chosen position, and clamps into the workspace when resized. Technical information is collapsed under Details. Browser verification found the camera JSON exactly unchanged after selection and panel movement. Closing/reopening retained position (8, 513) and the full 848×759 canvas. All 93 JavaScript tests passed.

Failed geometric findings and environment-asset controls retain automated coverage but were not exercised with a failing/environment browser fixture in this run.

## Release integration with #19

Integrated `origin/main` at `84a00ef`, including comparison tabs. The option tools
share the viewer queue, control activity, cancellation and context. Both legacy
checkpoint comparison and option tabs retain the camera and editing target.
Review fixes cover read-only option listing during playback, aborting slow option
preparation/display, and rejecting ambiguous checkpoint-plus-option inspection.
A second review caught a UI cancellation retry; display epoch checks now prevent
retrying an option installation after navigation cancels it.

Actual WebMCP checks against a fresh disposable workbench project:

- Created a saved option, renamed it, activated it, and verified the editing ID.
- Restored the six-foot checkpoint as a new checkpoint; the original and prior
  seven-foot history remain present. The restored build completed and appeared.
- Inspected the wider option and compared the full returned camera JSON with the
  pre-switch context: exactly equal.
- Prepared and started a tour, called `list_options`, and confirmed playback still
  reported `playing`.
- Reloaded the page and verified no playback toolbar appears before preparation.

Create/activate/restore can outlast the browser transport timeout. Their state was
verified with `versions.list` before continuing; no timed-out mutation was retried.
The earlier activation acceptance limit is resolved by this release run.

## Local sequence player (follow-up)

Implemented `sequence.prepare/play/pause/resume/replay/next/previous/stop/dismiss/status`
and replaced the provisional `camera.sequence`. Prepared subject bounds produce
perspective overview/detail/front/side/top angles, with coordinated mesh position,
visibility fades, highlights, camera transitions and timed holds. The ready card
waits for Play. Playback is local and returns tool results immediately. Direct
camera mutations pause the timeline. Stop interrupts active camera movement;
Close removes the player. Presentations are revision-bound and page-session-local.

Actual WebMCP and browser UI checks against the isolated workbench fixture:

- Prepared five steps / 30 seconds without starting playback or taking control.
- Clicked Play, Pause, Resume, Replay and Previous through the rendered controls.
- Completed all five steps with 12 parts visible and explosion off.
- Observed exactly `[true, false]` for the control class over a complete replay;
  there was no release/reacquire between shots.
- Confirmed paused camera JSON stayed identical while idle.
- A direct camera move paused the tour; front orthographic view resumed into the
  perspective presentation.
- A browser test clicked the player's Stop during an active camera move; the tool
  returned `CONTROL_STOPPED` immediately.
- Invalid part preparation returned `PART_NOT_FOUND` and retained the ready tour.
- Visually inspected the dark playback card and complete design in the browser.
- Final browser state: “Inside the workbench,” ready at step 1 of 5, 30 seconds.

Regression coverage includes remaining hold time, replay, no background movement
while paused, revision invalidation, manual camera adjustment, projection changes,
preflight restoration, reduced motion, moving highlight updates and Stop bypassing
queued camera work. Framing is based on bounds and preset angles, not collision
avoidance; captions are text, not synthesized speech.
