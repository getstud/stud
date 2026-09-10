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

A repeated key returns the existing operation. Capture source again after an edit; a source ID covers the entry point, declared Python helpers and inputs, not quotes. `finish` freezes matching source and records and saves exactly one changed checkpoint. Read its job outcome; a saved generation failure is not a successful model.

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
