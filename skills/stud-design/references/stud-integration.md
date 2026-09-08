# Stud integration

Use this reference when establishing a project, operating the build/viewer loop, or choosing validation APIs. Verify the installed version: Stud evolves, and its README, CLI help, `docs/validation.md`, and implementation are authoritative.

## Locate and operate

Typical checkout markers are `stud_cli.py`, `stud/`, `build.py`, and `web/`. The model API may live in `clubhouse/__init__.py` and be re-exported by `stud`; this historical package name does not constrain the design domain. Reusable builders currently live in `stud/assemblies.py`.

For the desktop app, use the installed `stud` command; it selects the bundled Python and engine. App resources are under `Contents/Resources` on macOS and the installation directory on Windows. API sources and documentation are in `engine/` there. Keep projects outside the app.

Commands below use placeholders for verified absolute project paths:

```sh
stud init /path/to/new-project --name "Project name"
stud build /path/to/project
stud serve /path/to/project --port 8766
stud validate /path/to/project --json
stud validate /path/to/project --strict
```

For a source checkout, replace `stud` with `python3 /verified/path/to/stud_cli.py`.

Initialization requires a new destination; editing an existing design uses its current project directory. Choose an unused port and reuse the server for subsequent edits. Use the CLI rather than an ad hoc import of build internals from an arbitrary working directory; the CLI establishes the checkout import context.

`design.py` must export the variable `project`. Helpers alongside it, or under `src/`, are supported by the current source watcher. Preserve `annotations/comments.json` and `annotations/prices.json` with the project.

## Observe the right revision

- `/api/model`: current successfully compiled model and revision.
- `/api/validation`: latest findings, coverage and possible build error.
- `/api/comments`: saved model feedback; use stable referenced part IDs.
- `/api/pricing`: quantities, quotes and unpriced lines.
- `/api/parts.csv`, `/api/materials.csv`, `/api/costs.csv`: generated exports.
- `output/model/validation.json`: local report, also written when validation fails.

An invalid build retains the last good model/CSV exports. Compare the report revision with the displayed model before interpreting highlights or claiming a correction is live.

Project Python changes normally rebuild automatically. Viewer JavaScript/CSS changes require a browser reload. Server or watcher changes require restarting that server. Use the available browser-control tool to interact with the existing tab; API reads can inspect data without browser navigation.

## Validation details to look up

Read the bundled `engine/docs/validation.md` (or checkout `docs/validation.md`) for current schemas, tolerances, scopes, exceptions, supported solids, and coverage semantics. Check the builder implementation when using generated requirements.

- New starters currently enable `solid_collision` and `stock_fit`; existing projects may retain narrow legacy checks.
- New measured checks support rotated boxes, linear profiles, gable notches and supported rafter seats. Legacy rules can have narrower rotation support.
- `minimum_contact` can constrain world-space face normal and minimum area; configure it from the actual mating requirement.
- `panel_support` checks rectangular-panel edge bands and support unions. Tongue-and-groove action and grain direction are not inferred; profiled panels may remain unverified.
- `framed_opening` expects the host wall to remove displaced field studs and cut its plates. Its result can tag later host parts with `include_in_clearance(...)`. Pass original stud IDs and local positions for supported cripple generation.
- A documented collision exception remains a warning. An automatic collision rule still runs independently of exceptions on another scoped rule.
- Strict validation currently returns 1 for failure, 2 for warnings/unverified results, and 0 for a clean report. Check actual output rather than interpreting every nonzero code as the same failure.

When an installed version lacks a needed check, add a focused project-level check or report the requirement as unverified. A whole application upgrade is not implied by an ordinary model edit.
