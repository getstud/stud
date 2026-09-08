# Reusable framed openings

For full floor, wall, roof and product-unit builders, see [Construction assemblies](construction.md).

`stud.framed_opening` creates a rectangular two-ply header opening and declares
its geometric requirements from the same dimensions. Door and window openings
use the same builder. Inputs and stock sections are actual inches.

```python
from stud import Project, WallFrame, framed_opening

project = Project('Workshop wall')
project.stock('stud', '2×4', '#ddbd8b',
              section=(1.5, 3.5), lengths=(96, 120))
project.stock('header', '2×8 header — provisional', '#d6ad78',
              section=(1.5, 7.25), lengths=(96, 120))
project.stock('spacer', 'Header spacer stock', '#baa382', sheet=(48, 96))

window = framed_opening(
    project, 'wall.north.window.1',
    frame=WallFrame(origin=(0, 0, 7.75), angle=0, inward=1),
    start=24, width=36, bottom=40, height=36, wall_height=96,
    stud_stock='stud', header_stock='header', spacer_stock='spacer',
    field_studs=[('wall.north.stud.02', 32), ('wall.north.stud.03', 48)],
)

# Host-wall parts added later can participate in the same clearance check.
project.box('wall.north.plate', 'Wall framing', 'stud',
            size=(120, 3.5, 1.5), origin=(0, 0, 7.75))
window.include_in_clearance([project.parts[-1]])
header_id = window.roles['header.0']
left_jack_id = window.roles['jack.left']
```

The example is a partial wall. The host design supplies plates, field studs,
connections and its other requirements.

## Placement and generated members

`WallFrame` defines local U along the wall, V into the wall, and Z upward from
the floor datum. `angle` rotates U around world Z in degrees. `inward=-1`
mirrors the depth direction. Cardinal and arbitrary horizontal orientations
are supported; walls tilted away from vertical are not supported.

`start` and `width` define the clear horizontal extent; `bottom` and `height`
define the clear vertical extent. Set `bottom=0` for a door. The builder uses
one bottom plate and two top plates, each as thick as the stud's smaller
cross-section dimension. `wall_height` includes these plates.

Generated roles are `king.left/right`, `jack.left/right`, `header.0/1`,
`header.spacer` when needed, `sill` for raised openings, and optional cripples.
Two header plies sit at the wall's depth faces. Spacer thickness is the
remaining depth; its material and construction must be specified by the design.
The header stock's larger cross-section dimension becomes its vertical depth.

The host removes displaced field studs and cuts the bottom plate for doors.
Optional `field_studs` pairs give original stable IDs and local U positions
wholly within the clear width. The builder creates `.lower`/`.upper` replacements
where there is space. It does not discover or modify unrelated existing parts.
Invalid builder inputs are rejected before generated parts/checks are committed.

## Generated checks and coverage

Each opening produces five declared requirements:

- Four bearing checks: each header ply must have bottom-face contact with each
  jack, over the full nominal area of jack thickness × ply thickness.
- One clearance check: selected framing and finishes must leave the rough
  opening volume clear.

These measure fit, not adequate load capacity. They do not verify jack-to-plate
support, sill/cripple support, header capacity, fasteners, flashing, or the rest
of the wall's load path. Add those requirements separately as they are designed.

Generated members carry `component`, `role`, and `validation_scopes` metadata.
The returned object's `roles` maps semantic roles to stable part IDs. Use
`include_in_clearance(parts)` for host framing and finishes; rule scopes resolve
against the final model, including later additions. Replacement parts must
retain or receive scope tags. Intentionally occupying door/window units should
not join this clearance scope. Collision checks remain independently applicable.

Rules have stable IDs such as `wall.north.window.1.bearing.0.left`, plus builder
name/version and component provenance in `source`. The same version appears
in exported findings. Rule IDs survive reordering or resizing an opening.

`validation.requirements` records which explicit checks are required. Missing
checks produce `UNVERIFIED`; failed checks remain failed. Automatic or unnamed
checks cannot satisfy an explicit requirement through a generated-ID match.
Duplicate explicit rule IDs are configuration failures. The viewer shows
requirement results separately from part participation coverage.

A new project with no validation configuration gets collision and stock-fit
checks when this builder is used. Existing validation settings are preserved.
The builder appends its declarations, so configure the project **before**
calling it; replacing `project.validation` afterward removes those declarations.

Use stable part IDs when migrating a design to these builders. Shared builder
edits are watched by the local server and apply on the next rebuild.
