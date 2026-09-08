# Stud integration

Use this reference when creating a design project, operating the build/viewer loop, or configuring design checks. Use the installed `stud` command and its bundled modeling documentation.

## Locate and operate

Verify `stud --version` and `stud --help`. Use `stud projects --json` to find remembered projects when the target folder is unknown. Keep design projects outside the app installation. If the command is unavailable, enable it through Stud’s desktop setup before continuing.

Commands below use placeholders for verified absolute project paths:

```sh
stud init /path/to/new-project --name "Project name"
stud build /path/to/project
stud serve /path/to/project --port 8766
stud validate /path/to/project --json
stud validate /path/to/project --strict
```

Initialization requires a new destination; editing an existing design uses its current project directory. Choose an unused port and reuse the server for subsequent edits. Run these commands against the design project folder; the installed command supplies the runtime.

`design.py` must export the variable `project`. Helpers alongside it, or under `src/`, are supported by the automatic rebuild watcher. Preserve `annotations/comments.json` and `annotations/prices.json` with the project.

## Observe the right revision

- `/api/model`: current successfully compiled model and revision.
- `/api/validation`: latest findings, coverage and possible build error.
- `/api/comments`: saved model feedback; use stable referenced part IDs.
- `/api/pricing`: quantities, quotes and unpriced lines.
- `/api/parts.csv`, `/api/materials.csv`, `/api/costs.csv`: generated exports.
- `output/model/validation.json`: local report, also written when validation fails.

An invalid build retains the last good model/CSV exports. Compare the report revision with the displayed model before interpreting highlights or claiming a correction is live.

Project Python changes normally rebuild automatically while `stud serve` is running. Use the available browser-control tool to interact with the existing tab; API reads can inspect data without browser navigation.

## WebMCP viewer review

Open the URL from `stud serve` in the connected browser and discover the tools exposed by that viewer tab. Stud exposes one WebMCP site tool, `show`; it needs no separate MCP server. Use the browser’s site-tool interface to invoke it.

- `{}` frames the complete design in perspective.
- `{"part_ids":["frame.stud.01"],"view":"front"}` frames and outlines specific parts. Use IDs from the current model, replacing this example ID.
- `{"region":{"min":[0,0,0],"max":[24,24,96]},"view":"perspective"}` frames and outlines a joint or area.

Supply either `part_ids` (1–100 unique IDs) or `region`, or neither for the whole design. Region coordinates are inches in world X/Y/Z; each maximum must exceed its minimum. Views are `perspective`, `front`, `side`, and `top`. Add `expected_revision` using the successfully built model’s revision when reviewing a specific edit.

`show` reveals all assemblies, exits exploded and transparent display, and clears previous highlights while retaining surrounding geometry. A single targeted part is also selected in the inspector. Use targeted views to explain connections and changes; use `show` with no target or **Fit model** to return to the full design.

Check `ok` and the returned `model_revision`. A successful call confirms the displayed model, not geometric correctness or user approval. On `ok: false`, inspect the structured error: correct stale IDs, reconcile a revision conflict with the latest build, or resolve a build error before retrying. A failed rebuild can leave the previous valid model visible.

If WebMCP is unavailable, use the viewer’s normal controls and verify the displayed revision. `show` controls presentation; edit geometry in the project files and read findings, comments, or prices through the project reports or local API described above.

## Modeling documentation

The installed app bundles design documentation under `engine/docs/` in its resources (`/Applications/Stud.app/Contents/Resources` for a typical macOS installation; the installation directory on Windows). Read only the guide needed for the current design step:

- `workshop.md`: creating parts, materials, dimensions, comments, pricing, and exports.
- `assemblies.md`: using the wall and opening assembly helpers.
- `validation.md`: configuring requirements, tolerances, scopes, exceptions, and interpreting coverage.

Use the modeling sections of these guides with the installed CLI workflow above. Use documentation matching the installed version. If required documentation or a capability is unavailable, state the gap and continue with supported design operations where possible.

## Design caveats

- Opening helpers require host-wall preparation: remove displaced field studs and cut the bottom plate for doors. Consult the bundled `assemblies.md` when adding an opening.
- Collision exceptions remain warnings; an independent automatic collision check still evaluates the same parts. Consult the bundled `validation.md` when configuring intentional joints.
- If supported checks cannot establish a required relationship, report it as unverified. Keep supplemental project calculations distinct from Stud’s validation results. Consult `validation.md` for shape limitations and supported rules.
