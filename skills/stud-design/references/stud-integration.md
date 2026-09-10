# Stud integration

Use this reference for the installed CLI, project lifecycle and precise version targeting. Run `stud --help` and the relevant command's `--help` for its current flags.

## Installation and format

Run `stud --version` and `stud doctor`. Desktop resources include Python, CadQuery, PDF dependencies, Git, and the engine/docs/examples. In a source checkout, install the pinned requirements into Python 3.13 and set `STUD_PYTHON` to that interpreter.

The current format is identified by `stud.json`. `design.py` exports `model` from `stud.cad.Model`. Legacy projects without that manifest use the older API exporting `project`, with inches and `annotations/`; keep their existing API. Read `docs/workshop.md` only for legacy authoring, and `docs/cadquery.md` for the current format. These files are bundled under `engine/docs/` in desktop resources.

## One request, one editing workspace

Use verified paths and IDs returned by commands in place of these placeholders:

```sh
stud init /path/to/project --name "Garage workbench" --example workbench
stud serve /path/to/project --no-open
stud status /path/to/project
stud begin /path/to/project --expected-head HEAD_FROM_STATUS --intent "Widen the bench" --key request-unique-key
# Edit design.py inside the returned workspace.
stud source /path/to/project --request REQUEST_ID
stud evaluate /path/to/project --request REQUEST_ID --source SOURCE_ID --wait
stud finish /path/to/project --request REQUEST_ID --source SOURCE_ID --summary "Wider bench" --wait
```

A repeated key returns the existing operation. Capture source again after an edit; a source ID covers the entry point, declared Python helpers and inputs, not quotes. `finish` freezes matching source and records and saves exactly one changed checkpoint. Evaluate and wait before finishing; `evaluation_required` means the current source has no completed evaluation. Read the findings before retrying. A saved generation failure is not a successful model.

`stud job --id JOB_ID --wait` follows an operation. `stud cancel --request REQUEST_ID` stops acceptance of its builds and preserves the workspace. `stud stop` closes the project's detached coordinator. A status read never executes geometry.

## Viewer and feedback

Open the URL printed by `serve` in the chosen browser and reuse the tab. Current APIs live under `/api/v1/`: `status`, `model`, `events`, `prompts`, `prices`, `checkpoints`, and `options`. All project actions go through the loopback coordinator; browser writes require the same origin and JSON content type, and the CLI uses that same JSON command endpoint.

`stud prompts` reads feedback without submitting it to an agent. Prompts retain IDs, original targets, source/build anchors and screenshots. Use `finish --addressed-prompt PROMPT_ID` to associate completed work. A deleted object or reference stays unresolved and retains its original capture.

For deliberate focus, write a JSON input using actual IDs:

```json
{"expected_build":"BUILD_ID","objects":["bench.top"]}
```

Then run `stud show /path/to/project --input focus.json --wait`. A result waiting for a viewer is not an acknowledgement. Regions in this native command use the project units from `stud.json`. The browser WebMCP presentation adapter uses its documented viewer coordinates; use the native CLI for project-coordinate focus.

For a native measurement:

```json
{"build_id":"BUILD_ID","source_id":"SOURCE_ID","targets":["beam:start","beam:end"]}
```

Run `stud measure /path/to/project --input measurement.json --wait`. Named references resolve against the archived native shape. Picked measurements include the object and point in native project units (`in` or `mm`) and report snapping/tolerance evidence. Stale/missing targets produce explicit errors.

## Alternatives and packets

`stud checkpoints` and `stud options` list stable identities. `stud inspect --checkpoint COMMIT --wait` changes the read-only displayed version; `stud live` returns to the current design. Neither changes an active writer.

`stud compare --left COMMIT --right COMMIT --mode historical --wait` uses each original saved estimate. `--mode common_price` uses one explicit saved quote basis and each design's own quantities/assumptions. Old estimates are not recalculated to masquerade as originals.

Create an option with `option-create --base COMMIT --name NAME`. Activate with `option-activate --option OPTION_ID --expected-head HEAD` once any writer is finished/canceled. `restore --checkpoint COMMIT --option OPTION_ID --expected-head HEAD` begins a new request from old design inputs; evaluate and finish it normally. Quotes and review history remain project-wide.

`stud plans --checkpoint COMMIT --build BUILD_ID --paper letter --wait` returns an immutable PDF, parts/material CSVs and manifest. Omit `--build` to let the coordinator locate compatible checkpoint geometry. An unavailable original runtime is an explicit reproduction limitation. Print at 100% and check the calibration line; for software acceptance, render every PDF page.


## WebMCP viewer control

Reuse the project’s open viewer tab and discover its exposed WebMCP site tools.
They need no separate MCP server. Installed versions can expose different tools;
the discovered schema is authoritative for arguments and supported actions. If
WebMCP is unavailable, use the existing viewer controls or the native CLI.

Start with `viewer_context`. Distinguish the **displayed version** from the
**editing target**; inspection can show an older design while a writer remains
active elsewhere. Resolve natural references to exact part IDs. When several
parts match, highlight the candidates and clarify the target before changing it.
Pass the returned `model_revision` as `expected_revision` on targeted actions.
Re-read context after a revision conflict instead of blindly retrying.

WebMCP camera inputs use model axes in **inches: X width, Y depth, Z up**, including
for metric projects. Returned camera snapshots explicitly use viewer axes
**X right, Y up, Z toward front**. Convert axes before reusing a snapshot as camera
input; do not pass native millimeter coordinates directly. Read the units attached
to measurements and estimates rather than deriving them from display formatting.

| Tool | Use |
|---|---|
| `viewer_context` | Read displayed/editing identities, camera, visibility, selection, matching parts and available capabilities. |
| `show` | Deliberately refresh and frame the whole design, exact parts, or a region. It reveals geometry and resets exploded display; reserve it for deliberate review rather than staged building. |
| `viewer` | Hide, reveal, isolate, select or highlight parts; explode/reset; toggle dimensions; open assembly drawings and mounting levels; control environment visibility and report pages. |
| `camera` | Immediate preset, fit, pose, move, orbit, zoom or back. Timed moves accept duration; stop interrupts control. Back is transient viewer history for the displayed revision. |
| `inspect_parts` | Read stock/finished dimensions, cut specifications, operations and mounting heights. `show:true` also reveals and frames the subjects. Preserve the distinction between a shaped part and its stock blank. |
| `checks` | Read findings and coverage for the displayed revision, highlight a named rule, or hide warning details. Explain relevant failures and gaps, not only the pass count. |
| `estimate` | Read prices, quantities, purchase units, allocation, missing prices and assumptions directly into conversation. Use exact row keys for manual price/quantity overrides or clearing them. |
| `versions` | List options/checkpoints; inspect, return live or compare; explicitly create, rename, activate or restore an option. Follow the schema’s head/revision guards. |
| `plans` | List packets or generate an immutable packet for a saved checkpoint; deliver the returned PDF/CSV links and completeness findings. |
| `sequence` | Prepare and control a local guided presentation as described below. |

The option comparison feature also exposes `list_options`, `switch_option`,
`compare_options` and `return_to_editing_view`. Use the discovered schemas to resolve
option names and switch the displayed design at the same viewpoint. These share
the viewer control lifecycle and preserve the active editing target.

Answer read-only questions without navigating away from the user's view. Estimate
writes require the live editable estimate, an exact row key, and its current
identity when supplied; historical estimates are read-only. Inspection and
comparison preserve the editing target. Activate only when the user intends to
change the editing option, with its expected head; inspect or compare for review.
A restore creates new history rather than overwriting an old checkpoint.

Use explicit saved checkpoints for plan delivery. If generation times out, check
`plans.list` for the completed packet before generating another. Likewise, a
completed mutation with a display/refresh warning should be verified, not repeated.
Treat `CONTROL_STOPPED` as user interruption: leave the current view alone and wait
for direction. Accepted server jobs can finish after presentation is canceled.

### Guided presentations

Use `sequence.prepare` for a walkthrough, assembly reveal or coordinated review.
Prepare a title and named steps using resolved part IDs. Each step can specify
`part_ids`, `view` (`overview`, `detail`, `front`, `side`, `top`), transition
`duration`, `hold`, an optional `caption`, and scene changes: `reset`, `explode`,
`hide`, `reveal`, `highlight`. Reveal the subjects before framing them. Preparation
requires perspective mode and validates all subjects while preserving the starting
view. Discover and respect the schema limits; the current player allows 20 steps
and 180 seconds total.

Preparation shows a ready toolbar without starting motion. Leave it ready unless
the user asked to play now; invoke `sequence.play` for that request. The local
player coordinates camera movement, exploded positions and visibility fades in
one continuous control session. Captions are text, not synchronized speech.
Reduced-motion preferences retain timed holds with still shots.

The minimal toolbar exposes Previous, Play/Pause, Next, Replay and Close:

- Pause releases manual control and retains the current step. Resume continues
  from the current view, including a camera adjustment made while paused.
- Previous/Next show the selected step and stay paused. Replay restores the
  prepared starting scene and starts again.
- Close maps to `sequence.dismiss`: interrupt control and remove the player while
  leaving the current view in place. The API also exposes `stop`, which retains
  the toolbar; it is not a separate toolbar button.
- Direct camera commands pause playback. Header tabs remain available; changing
  pages interrupts control and pauses the tour. Returning to Workspace allows
  resumption. Respect that interruption rather than restarting automatically.

Read `sequence.status` to distinguish ready, playing, paused, completed and failed
playback; a successful play call acknowledges starting, not finishing the tour.
A changed model revision requires a new preparation. Sequences are local to the
page session and are lost on reload. Subject framing uses bounds and preset angles;
it does not infer rooms, avoid walls or establish a safe interior route.
The dedicated `sequence` tool replaces the provisional `camera.sequence` action.
