# Workshop guide

This document describes the legacy inch-based `Project` API for existing projects. New projects use CadQuery and explicit request workspaces: follow [CadQuery projects](cadquery.md). `stud init` now creates the current format; do not paste legacy `Project` source into its manifest without an explicit conversion.

A local, agent-first design workshop. Define named parts in Python, inspect them in 3D, check geometry, export material takeoffs, and keep comments and supplier quotes alongside each project.

## Desktop app

stud's Tauri v2 app bundles the engine, Python, viewer, and native CLI for macOS
and Windows. Install the app, enable the `stud` command, and use it from Codex;
open the local viewer URL in Codex's in-app browser. The setup window also checks
for signed updates from GitHub Releases when a release channel is configured.

See [desktop installation, builds, and releases](desktop.md).

## Get started from source

Requires Python 3.10+ and Node.js/npm. No third-party Python packages are needed.

```sh
npm ci
npm run stud -- init ../my-workshop --name "My workshop"
npm run stud -- serve ../my-workshop
```

Open http://127.0.0.1:8765. stud opens the project directory you select; the app checkout contains no default design.

## Create another project

From this checkout:

```sh
npm run stud -- init ../my-workshop --name "My workshop"
npm run stud -- serve ../my-workshop --port 8766
npm run stud -- build ../my-workshop
npm run stud -- validate ../my-workshop --json
```

Optionally run `npm link` in this checkout to install the `stud` command on your machine. Then use `stud init ./my-project`, `stud serve ./my-project`, `stud build ./my-project`, and `stud validate ./my-project`. Each command also works through `python3 /path/to/stud_cli.py`. Set `STUD_PYTHON` to choose the interpreter used by the npm launcher.

`init` requires a new directory and creates a small starter model. Each project has its own `design.py`, `annotations/comments.json`, `annotations/prices.json`, and generated `output/model/` files. Serve multiple projects on different ports. Keep annotations when copying or backing up a project.

## Modeling

```python
from stud import Project

project = Project('My frame')
project.stock('2x4', 'Untreated 2x4', '#ddbd8b',
              section=(1.5, 3.5), lengths=(96, 120, 144))
project.box('frame.stud.01', 'Frame', '2x4',
            size=(1.5, 3.5, 80), origin=(0, 0, 0))
project.dimension('Height', (-4, 0, 0), (-4, 0, 80))
```

Units are inches; X is width, Y depth, Z elevation. Use stable unique part IDs. Python designs can import helpers alongside `design.py`. The existing `from clubhouse import Project` API remains compatible.

Coverage materials use each part's largest face area, including sloped faces
and trapezoidal sides for profile boxes. Rotation and assembly names do not
affect quantities. This is a single-face purchase allowance, not total surface
area or a cutting layout. Set `category='Furniture'` (or another project-defined
label) on `project.stock(...)` to group pricing rows; the default is `Other`.

Use [reusable framed openings](assemblies.md) to create kings, jacks, headers, sills and cripples together with their bearing and clearance checks. The builder supports resized, rotated and mirrored wall layouts and exposes named part roles.

The viewer rebuilds after project Python files change (top-level files and `src/` helpers). Invalid builds keep the last good preview and exports. Refresh for viewer JavaScript/CSS changes; restart for server changes. Designs are executable Python: open only trusted local projects. The server binds to loopback.

## Viewer and outputs

Orbit, pan, zoom, use orthographic views, isolate assemblies, inspect parts, and add persistent comments. The costs table supports quotes, quantity overrides, and spreadsheet paste. JSON and CSV exports come from the same model revision.

- `GET /api/model`: compiled model and revision.
- `GET /api/parts.csv`, `/api/materials.csv`, `/api/costs.csv`: exports.
- `GET/POST /api/comments`: project feedback.
- `GET/POST /api/pricing`: saved quotes and project estimates.

Validation checks declared geometry relationships, not structural suitability or code compliance. Stock packing is conservative; sheet quantities are area estimates, not cutting layouts. A new starter has no declared relationships and reports unverified coverage. `validate --strict` exits 2 for warnings or unverified work, 1 for failures, and 0 otherwise. Build refuses to replace model exports on validation failures.

## Development

```sh
npm test
node --check web/app.js
npm run stud -- init /tmp/stud-example
npm run stud -- build /tmp/stud-example
```

The original entry points (`serve.py`, `build.py`, `validate.py`) still work and accept `--project /path/to/project`. Project creation and selection are currently command-line operations; the browser is the modeling review workspace. The desktop app bundles these entry points and their runtime; source-checkout commands remain available for development.

## App and project ownership

This repository contains the stud engine, viewer, CLI, documentation, and generic tests.
Designs are separate folders containing `design.py`, helper modules, `annotations/`, and project documents. They can live anywhere and have their own Git repositories. App tests create temporary models and do not require local designs.

`projects/` is an ignored convenience folder for local designs. No designs are
included in this repository. Keep each project's source, annotations, and
reports in its own repository or backup; generated `output/model/` files can
be rebuilt.

All commands default to the current working directory when no project is supplied. Run the CLI by its absolute path when working outside this checkout. The `clubhouse` Python module remains a compatibility import; the modeling engine lives in `stud/model.py`.

## Validation and coverage

New projects automatically check solid collisions and stock fit. Add measured contact, panel support, opening clearance and face alignment requirements; the viewer’s **Checks** section shows findings, highlights and coverage by assembly. See [the validation guide](validation.md) for schemas, tolerances, exceptions and supported geometry.

## Show a design with WebMCP

In a compatible browser, stud registers `show` alongside the [hands-free viewer tools](voice-viewer.md). It presents the
current project's latest valid model in the shared viewer. No separate MCP
server is needed. Browsers without WebMCP retain the normal interface.

- `{}` frames the whole design in perspective.
- `{"part_ids":["frame.stud.01"],"view":"front"}` frames and outlines specific parts.
- `{"region":{"min":[0,0,0],"max":[24,24,96]},"view":"perspective"}` frames and outlines a region.

Use either `part_ids` (1–100 unique IDs) or `region`, or omit both. Region
coordinates are inches, X width, Y depth, Z up; every maximum must exceed its
minimum. Views are `perspective`, `front`, `side`, and `top`. Optional
`expected_revision` rejects a different revision.

Showing reveals all assemblies, turns off exploded display, clears
previous highlights, and brings the viewer into view. A single targeted part is
also selected in the inspector. Surrounding geometry remains visible. Use
**Fit model** to clear the focus and return to the full design.

Success returns `ok`, `model_revision`, `project_name`, `view`, targeted
`part_ids`, the framed `region`, `units`, and `visible_part_count`. This confirms
what was rendered, not that the user saw or approved it. Invalid arguments,
missing parts, revision conflicts, and failed builds return `ok: false` with a
structured `error`. Failed rebuilds retain the last good model and do not report
a successful show. The tool does not modify designs, comments, or prices;
refreshing can rebuild the project's generated exports.

Registration follows the [Codex Site tools documentation](https://learn.chatgpt.com/docs/webmcp)
and uses `document.modelContext.registerTool` when available.

## Comment on an area screenshot

Click **Comment on an area** above the viewer, then drag a rectangle over the
frozen view. Add a comment to the cropped preview and save. Escape or Cancel
exits capture. This captures pixels (including visible dimension labels); it
never selects parts or tries to identify objects inside the rectangle.

Area screenshots appear with part comments in **Comments**. Click a thumbnail
to view the original capture, and resolve or reopen it like any other comment.
The saved image stays unchanged when geometry, visibility, or the camera changes.

Comments live in `annotations/comments.json`. An area comment has `kind: "area"`,
its captured `revision`, and `image` metadata with a relative `path`, pixel
`width` and `height`, and `mime_type`. Its PNG lives at
`annotations/screenshots/<comment-id>.png`. Keep the entire `annotations/`
folder with the project. Existing part comments remain compatible.

Tell the agent **“Read my comments”** when ready. It can read the comment JSON
and inspect each referenced PNG. Through the local server, comments are at
`GET /api/comments` and images at `GET /api/comment-images/<comment-id>`.
Saving a screenshot comment doesn't require the current design to build: its
image and revision describe the view that was captured. Captures are limited
to 2048 pixels on the longest side; the server accepts PNGs up to 5 MB and
4096 pixels per side. No new WebMCP tools or automatic notifications are added.

See [Environment assets](environment.md) for project-local procedural Three.js geometry, including a tree example.

## Construction builders

See [Construction assemblies](construction.md) for floors, backed and lapped walls, enclosure junctions, cut-rafter gable roofs and operating door/window units. Build bottom-up and review declared requirements before covering framing.
