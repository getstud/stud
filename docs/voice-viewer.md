# Hands-free viewer review

stud exposes the existing viewer operations through `document.modelContext` in compatible browsers. Speech belongs to the host conversation; no microphone or second chat UI is added. Every tool returns structured results and the current viewing context. Comments remain in the conversation and are excluded from these tools.

## Existing UI inventory

| Existing interaction | WebMCP equivalent |
| --- | --- |
| Fit design, frame a part or area | `show`; `camera.fit` |
| Search parts and identify a selection | `viewer_context` with optional `query`; `viewer.select`; `viewer.highlight` for clarification candidates |
| Assembly visibility and isolation | `viewer.hide`, `reveal`, `isolate`, `reset` with exact assembly names or part IDs |
| Exploded assemblies and dimensions | `viewer.explode`, `viewer.dimensions` |
| Part inspector, cuts, stock blanks and mounting heights | `inspect_parts`; `show:true` reveals and frames the requested parts |
| Assembly Plan/Front/Side drawings and mounting levels | `viewer.drawing`; `level:null` selects All levels; omitted level retains the existing filter |
| Orbit, pan, zoom, orthographic views and fly navigation | `camera.preset`, `pose`, `move`, `orbit`, `zoom`, `fit`, `stop`; `back` returns to the previous conversation-directed view |
| Environment visibility, inspection and fit | `viewer.environment`, `inspect_environment`, `camera.fit` with `environment:true` |
| Open/close parts browser and report pages | `viewer.parts_panel`, `viewer.page` |
| Warnings, finding details and coverage | `checks.read`, `show` with optional exact `rule`, `hide` |
| Estimate table, quantity and price evidence | `estimate.read` returns actual totals, completeness, row keys, stock sizes/allocation, purchase units, quantities, assumptions, quotes and gaps |
| Manual prices and quantity corrections | `estimate.set`, `clear_manual`, `clear_quantity`; the UI uses the same pricing endpoint and also exposes Reset quantity |
| Existing options and saved checkpoints | `versions.list`, `inspect`, `live`, `activate`, `create`, `rename`, `restore` |
| Existing two-pane comparison, orbit/pan/zoom and selection | `versions.compare`, `comparison_camera`, `comparison_select` |
| PDF generation, paper and compact/expanded layout | `plans.generate`; `plans.list` returns saved packets and downloadable files |
| Parts, materials and estimate report exports | `viewer_context.exports` exposes the existing CSV links; immutable packet lists come from `plans` |

Dot notation above means a tool's `action` argument, for example `viewer({"action":"hide","assemblies":["Roof"]})`. Theme and software-update preferences are app settings, outside design-review operations.

## Conversation contract

Start with `viewer_context`. It identifies the installed model revision, source/build/checkpoint, active editing option/request, camera, visible part IDs, selection, highlights, framed region, drawing, environment and current page. Its part search returns labels, assemblies, material IDs and world bounds. With no selection, an implicit part request fails with `AMBIGUOUS_REFERENCE`; highlight exact candidate IDs and ask which one the user means. Do not silently choose an arbitrary match.

Geometry, bounds, camera input coordinates and mounting levels use inches with X width, Y depth, Z up. Native CAD operations and purchasing specifications retain their explicitly labeled project units. The camera context labels its renderer coordinate system separately: viewer inches, X right, Y up, Z toward the front. Mounting height uses the lowest point of the entire design, including hidden parts. Cut specifications distinguish finished cuts from shaped stock blanks.

Use `expected_revision` on actions derived from earlier context. Tools reject stale revisions, unknown parts/assemblies, malformed inputs and invalid camera requests before applying the requested operation. The application remains usable when WebMCP is unavailable.

`versions.inspect` and `versions.compare` leave the editing option/request untouched. `versions.activate` explicitly chooses the editing option and requires `expected_head`. Restore uses the existing request/source/finish sequence to create a **new** checkpoint on the specified option; it never rewinds or discards history. Existing server guards reject activation/restoration while an editing request or pending records need completion. An inspected model, its cuts and its original estimate stay together. Historical estimate writes are rejected by both viewer and server.

`camera.back` is a bounded, in-session navigation history (30 actions), tied to the displayed revision. It retains the camera/projection, selection, visibility and drawing return state. Named saved views and saved section/print choices belong to #26.

Answer cost and quantity questions directly from `estimate.read`; opening the Estimate page is unnecessary. Report a complete total only when `complete` is true. Otherwise explain the known subtotal and returned `missing` reasons. Use the exact purchase row key when different lengths or specifications share a product name. A price-only correction preserves quantity; resetting the quantity removes its override and restores the calculated purchase count. Quote writes retain the server's estimate/build guards and idempotent transport retry.

`plans.generate` defaults to the displayed saved checkpoint and build. A draft without a checkpoint requires an explicit saved checkpoint; it never silently exports another version. Returned download URLs identify an immutable packet and include its PDF, parts/cut CSV, materials CSV, manifest and SVG drawings. The manifest retains source, checkpoint, build, price basis, print settings and completeness findings. Report links in `viewer_context.exports` are dynamic and describe the current displayed model at download time.

## Activity and feature ownership

The animated inner frame follows actual control execution and awaited rendering/job completion. Read-only context, measurements, checks, estimates and packet/version lists do not start the glow. Nested/overlapping actions hold it until all active work finishes. Exceptions release it. Reduced motion uses a static inner glow. Camera stop bypasses the command queue so it is not delayed by packet generation.

`web/viewer-tools.js` defines the schemas and shared tool runner. `web/viewer-operations.js` binds them to installed application state. `web/project-operations.js` shares version transport and job/restore operations with the Versions UI. `registerControlledTools(tools)` in `app.js` lets feature-owned tools use the same queue, glow and context wrapper. An option-tab adapter should receive `registerTools:registerControlledTools` and expose its controller through the viewer adapter's optional `optionComparison` hook.

#24 owns this existing parity inventory. #19 owns the new comparison tabs and their full voice interface. #20 owns new estimate presentation, sourcing and accuracy capabilities. #26 owns new saved views, sections and print selections. Each new feature must define representative conversation requests, expose its operations through WebMCP and verify both returned data and visible behavior.

While AI control is active, workspace chrome is hidden without changing the canvas layout. Pointer, wheel, touch-drag, and keyboard camera input are blocked while control is active, including comparison canvases. Recreated Orbit/Fly controls inherit the lock, and held flight keys are cleared. A bottom-center Stop pill restores the controls immediately, stops camera motion, aborts pending presentation, and discards queued tool calls. Already accepted server jobs may finish and retain their results; Stop does not undo saved project changes.

## Guided sequences

`sequence.prepare` creates a local presentation and displays a ready card. It does
not start playback. Each step accepts a label, optional caption, exact `part_ids`,
a viewing angle (`overview`, `detail`, `front`, `side`, `top`), transition `duration`
and `hold` seconds. Scene changes (`reset`, `explode`, `hide`, `reveal`, `highlight`)
are coordinated with the camera. All subjects are validated before preparation;
preparation restores the starting view. Sequences require perspective mode, contain
at most 20 steps and last at most 180 seconds. Reduced-motion users get still shots
with timed holds.

Use `sequence.play`, `pause`, `resume`, `replay`, `next`, `previous`, `stop`,
`dismiss`, or `status`. The on-screen controls use the same operations. Playback
runs locally with one continuous activity owner. Pause releases the camera; direct
camera commands also pause playback. Resume eases from the adjusted view. Stop
cancels active control immediately and leaves the current view in place. Replay
restores the prepared starting scene. Close dismisses the player. Changing the
model revision invalidates the presentation; prepare it again against the new
geometry.

The new `sequence` tool replaces the provisional `camera.sequence` action.
Individual camera commands remain available. Prepared presentations are scoped
to the current page session and are not persisted across reloads. Captions are text,
not synchronized speech. Framing uses subject bounds and preset angles; it does
not perform collision avoidance or infer interior routes.

```json
{"action":"prepare","title":"Inside the workbench","steps":[
  {"label":"Overview","reset":true,"view":"overview","duration":2,"hold":3},
  {"label":"Lift surfaces","explode":true,"duration":3,"hold":3},
  {"label":"Frame","hide":["bench.top","bench.shelf"],"view":"front","duration":3,"hold":3},
  {"label":"Back together","reset":true,"duration":3,"hold":3}
]}
```
