# Composing floor systems

`stud.framing` and `stud.floors` are installed construction APIs. Project Python
owns the design inputs; the library derives physical members, stock cuts,
connections, quantities, drawings and measurable requirements. Start with
`stud init PATH --example floor-system` for a complete editable fixture.

## Inputs and composition

- `MemberProfile(width, depth, product_id, stock_lengths, flange=0, web=0,
  unresolved=())` uses actual dimensions in project units. Both zero profile
  dimensions select solid stock; positive flange/web dimensions select a factory
  I section. Available lengths and product selection stay explicit.
- `Bearing(part_id, x, width, top)` describes a named support seat in the floor's
  local coordinates. Joists run along X, spacing follows Y, and Z is up. Seats
  run across the region in Y; native contact checks verify their actual extent.
- `Opening(id, x, y, length, width)` describes the clear void. Keep its ID stable
  across moves. Headers, trimmers, cut joists and later sheet cuts use this one
  definition. Crossing a bearing or overlapping complete opening framing needs
  a revised support scheme or explicitly shared framing.
- `HangerDetail(product_id, seat, height, thickness, unresolved)` supplies a
  generic U-shaped envelope. Seat bearing, host contact and interference are
  checked. Product-specific geometry, capacity and fasteners need their own
  evidence; the envelope does not establish a rated connection.

```python
floor = frame_floor(model, object_id='floor', length=length, width=width,
    joist=joist, rim=rim, bearings=bearings, spacing=spacing,
    min_bearing=min_bearing, openings=openings, opening_stock=header_stock,
    hanger=hanger, parent='building', unresolved=design_gaps)
```

Each region is rectangular, with matching-depth joists/rims and coplanar
transverse seats. Compose independently placed regions for wings, changed
directions or elevations. Arbitrary polygons, shared framing between overlapping
openings, continuous members over multiple bearings, and automatic structural
sizing are outside this builder's scope. Ordinary CadQuery and lower-level stock
operations remain available for those designs.

For irregular traced or authored outlines, `stud.framing_geometry` supplies
`offset_polygon`, `polygon_intervals`, `perimeter_stock`, and `clipped_member`.
Compose these with the same `MemberProfile` objects. Perimeter cuts retain stable
edge/piece indices, partition long blanks, clip explicit pockets, and report each
finished outline in that piece's stock axes. `clipped_member` preserves the
factory section while cutting the boundary and openings; disconnected results
require separately authored runs. These operations leave joist directions,
stations, opening spans and deliberate exceptions in project Python.

`AnchorDetail.shape(sill_depth=..., hook_length=..., nut_diameter=...)` and
`HangerDetail.shape(width, face_flange=...)` expose the shared hardware envelopes
for project-owned placements. `drill_anchor_pattern` retains a prescribed divided
station pattern with explicit candidate shifts and an optional clearance policy;
it returns accepted station IDs and contained bores. Missing stations still need
an unresolved layout record. `bearing_contacts` and `member_end_interfaces`
discover candidate interfaces; register native measurements for evidence. Angled
end contact area does not establish a product's required bearing length at every
flange point.

`anchored_sill(...)` takes top-center `start/end`, a solid `stock` profile,
`AnchorDetail`, named `support`, end/spacing constraints, and optional `avoid`
part IDs or forbidden center `exclusions`. It derives the bores and anchor
envelopes together, keeps hardware clear of neighbors and each other, measures
sill bearing, and records a specific gap when its anchor layout is incomplete.
Neighbor projections are conservative; an unresolved pattern may need another
detail or a project-specific layout. Anchor embedment geometry does not prove
concrete capacity or reinforcement compatibility.

Reserve anchor corridors with `deck_floor(..., seam_exclusions=[(x_min,x_max)])`;
the builder keeps the entire backing width outside those local X intervals.
Generate optional backing before laying out anchors, and include it in `avoid`.
Each operation also checks new geometry against existing
parts, so later backing cannot silently collide with earlier anchors. The named
anchor support is excluded from those interference checks because embedment is
intentional. Re-execution resolves named support targets after all operations.

## Panel flooring

Use `deck_floor(model, floor, panel=PanelSpec(...), backing=..., installation=...)`
with the result of `frame_floor`. `PanelSpec` owns product ID, actual thickness,
nominal `(width, strength-axis length)` module, optional actual sheet dimensions,
`edge="tongue_and_groove"` or `"square"`, and product selection uncertainties.
Its default module is `(48,96)` in project units; millimeter projects must supply
millimeter dimensions explicitly. T&G mates must share a joint family (defaults
to the product ID). Different products are not assumed compatible.

```python
from stud.floors import PanelSpec, BackingDetail, FloorInstallation, deck_floor

subfloor = deck_floor(model, floor,
    panel=PanelSpec('selected.tg_plywood', .703, actual_size=(47.5,95.875)),
    backing=BackingDetail(backing_stock, 'Use selected joist-compatible end attachment.',
        unresolved=('Resolve backing connection capacities and fasteners.',)),
    installation=FloorInstallation(
        fastening='Project fastening schedule', adhesive='Selected subfloor adhesive',
        joint_gap=.125))
```

Geometry uses touching nominal modules. Installation joint allowances and actual
sheet sizes remain separate metadata; they do not introduce tiny gaps or tongue
solids. A `nominal_sheet_layout` fabrication finding explicitly prevents these
layout envelopes being mistaken for verified shop cuts. Sheet counts are explicit
assignments, without offcut optimization or a complete fastener/adhesive order.

The library staggers adjacent courses by half the sheet length and starts square
ends on the rectangular frame's first joist station. `DeckRegion` can override
origin, angle and stagger to suit a different grid. It preserves the chosen grid;
where square ends lack support, it creates local backing from `BackingDetail`.
No backing stock is inferred from rim stock. Omitting backing leaves unsupported
edges as native findings. The library does not relocate framing or size members.

For composed floors, use `FloorSurface(outline, supports, top, openings=...,
location=...)` with an explicit deck `object_id`. Outline, top and openings use
surface-local coordinates; support IDs name existing physical members. Pass the
same `Opening` objects to framing and decking. `DeckRegion(id, outline=None,
origin=(0,0), angle=0, stagger=None)` defines each sheet orientation. Its local X
follows sheet width and Y follows the strength axis. Explicit region polygons
must not overlap; one region may omit its outline to receive the remaining area.
The regions must cover the surface. These operations handle polygonal floors,
internal holes, disconnected cut pieces and independently rotated framing wings.

Each panel gets native `panel_edge_system` evidence. Every actual perimeter
interval must meet opposing framing contact or a compatible opposite retained
factory T&G edge. A cut, unmatched tongue, shifted panel or missing support
produces a normal inspectable finding. Factory edge identity lives in the original
panel blank and is clipped to current geometry; cutting an edge does not invent
a new tongue. Cache keys include all support/mate shapes, placements and factory
edge metadata. This is geometric interface evidence, not joint capacity analysis.

Try `stud init PATH --example subfloor-system` for an L-shaped floor with a shared
stair opening and a rotated wing. The older explicit
`product_id/thickness/sheet_size/gap` call remains compatible with saved
square-edge projects; use `PanelSpec` for new designs.

## Changes and evidence

Edit the owning Python input and re-execute the project. There is no dependency
graph to maintain: generated geometry, cuts, demands and requirements are rebuilt
together. Semantic opening/support IDs retain useful member identities; changed
topology can legitimately add or remove members. Native measurement caching
includes shapes, placements, policies and thresholds, so changed inputs cannot
reuse stale passing evidence. The final member rows are also checked for excessive spacing after opening/hanger exclusions; unresolved intervals prevent the geometry summary from claiming verification. A layout pass does not choose structural sizes.

The builder records expected parts, requirements and connections using
`model.expect(id, parts=[...], requirements=[...], connections=[...])`. These
inventories survive accidental removal of generated parts and their checks.
For project-owned operations, declare that inventory from intended work, rather
than scanning whatever outputs happened to survive.

Native `support` requirements accept `region_local={"min":[x,y,z],
"max":[x,y,z]}` in the supported part's original stock frame. This isolates each
end: adequate bearing at one end cannot conceal a missing seat at the other.
The bearing `direction` remains a world-space vector.

Builds and the viewer expose `design_review`: geometric verification is separate
from unresolved connections, material selections, fabrication data and missing
expected work. Missing expected parts or measurements invalidate the geometry
summary. “No recorded gaps” means exactly that; it does not establish structural
approval. Record sourced selections or explicit assumptions whether or not a
drawing exists. A drawing is optional evidence for the same design inputs.
