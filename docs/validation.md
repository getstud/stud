# Geometry validation in stud

stud checks declared geometric requirements, not structural capacity. Thresholds are project requirements in inches or square inches, not inferred code limits.

New starter projects enable collision and stock checks automatically. Existing projects opt in without changing their legacy rules:

```python
project.validation = {
    'version': 1,
    'automatic': ['solid_collision', 'stock_fit'],
    'rules': [],
    'unverified': [
        {'rule': 'connections', 'message': 'Connection design is not specified.'}
    ],
}
```

Automatic checks run over every part in the final model. Explicit scopes contain stable part IDs. A missing reference or empty scope fails rather than silently passing. The existing bearing, rafter-seat, rim, corner-lap and other legacy rules remain supported; legacy rotation limitations still apply to those rules.

## New measured rules

Add these dictionaries to `rules`:

```python
# Positive-volume interference; touching faces and edges are allowed.
{'kind': 'solid_collision', 'parts': ['wall.stud', 'ledger']}

# Actual opposing coplanar contact, optionally on a chosen world-space normal.
# Area threshold below is illustrative, not a structural specification.
{'kind': 'minimum_contact', 'parts': ['header', 'jack'],
 'normal': [0, 0, -1], 'minimum_area': 2.25}

# Second world-axis extremum minus first must equal the declared offset.
{'kind': 'face_alignment', 'parts': ['rafter', 'soffit.joist'],
 'axis': 2, 'faces': ['min', 'min'], 'offset': 0}

# A clear volume in the same coordinate system as parts. Deliberate occupants,
# such as door leaves or glazing, must be omitted from the candidate scope.
{'kind': 'opening_clearance', 'parts': ['stud', 'siding', 'bottom.plate'],
 'opening': {'origin': [36, 0, 7.75], 'size': [72, 3.5, 80]},
 'clearance': 0}

# Panel first, supports following. Bearing strips must be continuously covered.
{'kind': 'panel_support', 'parts': ['panel', 'rim', 'joist', 'blocking'],
 'thickness_axis': 2, 'bearing_width': .75}

# Lumber section, cut length and available length; sheet blank dimensions.
{'kind': 'stock_fit', 'parts': ['stud', 'panel']}
```

All new rules accept `id` for a stable rule identifier and a positive `tolerance`, default 0.001 inch. Collision findings report a separating translation along a solid axis; this is a geometric penetration measure, not a recommended move. Notched solids are decomposed, so reported penetration applies to the overlapping convex pieces.

`face_alignment` compares world-axis extrema. It establishes alignment, not contact, parallelism, fastening or support. Use `minimum_contact` alongside it where contact is required.

`panel_support` works with rectangular panels in any orientation, using their local minimum-thickness face as the underside. The two other local axes become edge axes 0 and 1. Optional `edge_widths`, such as `{'0:0': 1.5}`, override individual bands. Support coverage is a geometric union, so duplicate support faces cannot inflate coverage. Profiled/notched panels return `UNVERIFIED` rather than assuming a rectangle. Tongue-and-groove support and panel grain direction are not inferred.

`opening_clearance` accepts optional XYZ Euler rotation on the opening. `clearance` expands all three local dimensions equally. Use an explicit opening volume when directional clearances differ.

## Supported solids

The new solid checks support boxes, linear Y/Z profiles, gable notches under `profile.notch`, and existing world-Y/Z rafter seats. XYZ Euler rotations match the viewer. Positive-volume overlap is tested on the actual convex pieces rather than their bounding boxes. Bounds are used only to filter candidate pairs. Unsupported/invalid solid representations are reported rather than counted as checked collision geometry.

This is not a general CAD kernel: curved parts, arbitrary meshes, nonlinear profiles and assembly deformation are not supported.

## Exceptions and draft requirements

An intentional collision must name exactly two parts and explain why:

```python
{'kind': 'solid_collision', 'parts': ['a', 'b'],
 'exceptions': [{'parts': ['a', 'b'],
                 'reason': 'Intentional joint; cut geometry will be modeled later.'}]}
```

An exception remains a visible `WARNING`; it does not become a pass. To use exceptions for a complete model, omit automatic `solid_collision` and declare one scoped collision rule containing all parts and the exceptions. Otherwise the independent automatic rule will still reject collisions.

For a known incomplete draft requirement, an explicit rule can use:

```python
{'kind': 'minimum_contact', 'parts': ['rafter', 'plate'],
 'minimum_area': 1, 'normal': [0, 0, -1], 'severity': 'WARNING',
 'reason': 'Draft bearing seats remain to be designed; threshold only detects missing contact.'}
```

A warning-only rule requires a reason. This keeps incomplete work visible while allowing a draft preview. Use `unverified` for requirements that cannot yet be evaluated, such as loads, connections and product selections.

## Results, coverage and build behavior

- `PASS`: the declared geometric check passed.
- `FAIL`: a geometric requirement or rule configuration failed; model/CSV exports retain the last good build.
- `WARNING`: a documented exception or explicit draft rule needs attention.
- `UNVERIFIED`: the check cannot establish the requirement with the available geometry or information.

Coverage lists checked/total parts by assembly and separately for collisions, support, alignment, openings and stock. A participant counts as checked in a category when a rule ran with a pass, failure or warning. An unverified result does not count. “Any check” is not a completeness score: support coverage can be zero while collision coverage is complete. Missing semantic requirements cannot be inferred solely from assembly names.

The viewer's **Checks** section shows failures, warnings and unverified items by default, with filters for each status and passed checks. **Highlight parts** marks the relevant geometry; findings with a location also show an orange marker. Highlights are disabled when the finding belongs to a different revision from the displayed model.

- `output/model/validation.json`: report, including coverage and model revision, written even when geometric validation fails.
- `GET /api/validation`: latest report and a build error when the current edit cannot be built.
- `/api/model` includes `validation_results` for successful builds.
- `stud validate PROJECT --json` includes findings, counts and coverage.
- CLI exit codes: 1 for failures; with `--strict`, 2 for warnings/unverified results; otherwise 0.

New Python modules used by validation trigger rebuilds after the server is restarted to load the updated watcher. Reload the browser after viewer JavaScript/CSS changes.
# Assembly-generated requirements

The [framed-opening builder](assemblies.md) generates geometry, stable rule IDs,
provenance and five explicit geometric requirements per opening. Its clearance
rules combine explicit `parts` with parts tagged in the rule's named `scope`.
The validator resolves scopes against the final model. A requirement references
an explicitly named `rule_id`; missing checks report `UNVERIFIED` and duplicate
explicit rule IDs fail configuration. Reports expose these results in
`coverage.requirements`, separately from counts of parts involved in checks.
