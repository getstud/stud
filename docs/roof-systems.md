# Roof composition

Use `stud.roof_layout` for named top-of-framing planes and their visible XY
domains. Use `stud.roof_framing` to plan and register conventional members,
coordinate unspecified factory trusses, and fit mono-slope or equal-pitch gable
walls. Dimensions use the model's native units. There is no default site,
structural system, member sizing, truss spacing or drawing requirement.

Python remains the source of truth. Retain footprint, eave/heel datums, pitches,
bearing lines, stock and openings in a compact project specification. Change
those inputs and execute again; the layout and its consumers recompute. This is
not an incremental dependency engine. A plane or domain change requires a fresh
evaluation of its members, wall caps and interfaces.

## Planes and compound roofs

```python
from stud.stock import Plane
from stud.roof_layout import RoofFace, hip_roof_faces, layout_roofs

# Fixture inputs, not construction specifications. Outline is at the eaves.
main = hip_roof_faces('main', ((0, 0), (240, 0), (240, 144), (0, 144)),
                      eave_top=100, pitch=6/12)
addition = RoofFace('addition', Plane.roof(origin=(180, 0, 105), slope=(0, .4)),
                    ((180, 0), (280, 0), (280, 96), (180, 96)))
roof = layout_roofs((*main, addition))
profile = roof.section((0, 72), (280, 72))
```

`RoofFace(id, plane, outline)` retains immutable finite, convex polygons with
upward planes. Concave footprints compose from convex components. Hip faces use
the **minimum** of their inward-rising planes. `layout_roofs(faces)` resolves the
**maximum** of overlapping components, clips concealed domains, and retains the
original `faces` alongside visible `patches`. Coplanar overlaps have a deterministic
owner, independent of input order. Adjacent convex pieces coalesce where possible.
No member is generated merely because an underlying hidden plane exists.

`height_at(x, y)` returns `None` outside coverage. `section(start, end)` returns
ordered `RoofSegment(face, start, end)` values with XYZ endpoints; missing regions
remain gaps. These sections serve roof profiles, wall limits and coordination
drawings. A footprint boundary is not automatically a physical bearing line.

`roof_stations(layout, direction=..., spacing=..., origin=(0, 0))` returns integer
grid stations and their visible section profiles. Direction is the horizontal
member axis; spacing is perpendicular to it. Keep the origin fixed for edits.

`roof_edges(layout)` returns finite `RoofEdge(faces, start, end, kind)` records
for shared visible ridges, hips, valleys and slope breaks. It verifies agreement
in elevation, so overlapping XY edges at a roof-to-wall step do not become a
false ridge. Exterior eaves and bearing lines remain separate inputs.

## Conventional members

```python
from stud.framing import MemberProfile
from stud.roof_framing import RafterField, plan_roof_members, frame_roof

stock = MemberProfile(1.5, 7.25, 'fixture.rafter', (144, 192, 240),
                      unresolved=('Select grade, loads and span basis.',))
fields = tuple(RafterField(face.id, stock, 16, origin=(8, 8))
               for face in roof.faces)
plan = plan_roof_members(roof, fields)  # no Model mutation
# result = frame_roof(model, roof, fields, object_id='roof.rafters')
```

`RafterField` accepts `direction=None` (steepest rise), and `edge_setback=0`
(horizontal distance from patch edges). A level roof requires a direction.
Each `RoofMember` retains its source face, endpoints, stock profile and oriented
cuts. `cut()` returns a solid, placement and original stock blank. Compound end
cuts include the finite domain boundaries and top plane.

`frame_roof` registers these members, grouped stock demands, validity/stock checks
and expected inventory. Optional `bearings=(part_ids, ...)` plus a required
`bearing_length` cuts seat pockets from actual horizontal support faces and adds
native support checks. The original blanks retain the bearing cut operations.
Severed members raise an error; notch-depth/remaining-section limits and uplift
connections still require a selected detail. It **does not** select or build
supporting ridge/hip/valley members, ties or hardware. Its named end-detail finding
remains unresolved until the project composes those interfaces. A uniform setback
is not a substitute for the finite face of a selected hip or valley beam.
Concave visible domains can split a station into multiple physical pieces;
inspect those breaks and supply actual support or a continuous-member detail.

`cut_bearing_seats(stock_result, supports)` exposes the same seat operation for
hip, valley and other selected stock. `supports` maps stable IDs to world solids;
the result contains the revised stock tuple and touched support IDs. Declare
required bearing areas and notch/remaining-section evidence in the owning detail.

Use `Plane.intersection`, `cut_member` and `StockParts` for the selected ridge,
hip, valley and beam assemblies. Distinguish a ridge board plus thrust restraint
from a supported structural ridge beam. The existing `hip-roof` example remains
the more detailed conventional tied-hip joint study.

## Factory trusses

`truss_profile_envelope(model, profile, object_id=..., bottom=...,
diagram_diameter=..., parent=None, unresolved=())` creates one **coordination
outline** from a continuous section. Diagram strokes are thin round solids,
deliberately unlike rectangular lumber. `diagram_diameter` is display geometry,
not a chord section. Disconnected profiles require separate definitions.

The part carries `lineage.representation = 'coordination_outline'`, no lumber
blank or cut list, and a factory-truss demand with explicit unresolved shop data.
Its geometry-detail finding identifies missing manufacturer profile, spacing,
members, plates, bearings, reactions and bracing. The envelope is not the final
fabricated truss; do not treat its stroke volume as material quantity or its
outline as structural verification. Supplied shop members can later replace the
coordination representation under the project's retained truss identity.

## Roof-dependent walls

`roof_wall_limit(layout, centerline, depth=..., clearance=...)` returns a
conservative **level** wall height, measured above the `WallLine.base`. It clips
every visible patch to the full stock footprint. Clearance is vertical; missing roof coverage
raises an error. Use the roof section profile for sloping infill instead of
silently applying the shortest height to an entire gable.

`frame_sloping_wall(model, run, planes, object_id=..., floor_supports=(),
detail=None)` reuses a `WallRun` and its opening/header definitions below the
minimum of world-space **top-of-plate** planes. It supports one slope or an
equal-pitch gable. The bounding run height must reach the peak; stock blanks
are shortened to each actual cut member. It creates roof-cut studs and raking
double plates, checks stock, collisions and stud-to-cap contact, and rejects a
roof cut that damages a header, jack or sill before registering parts.

Roof top and plate top differ by the selected framing/seat/ceiling buildup.
Pass that relationship explicitly. The operation does not choose a clearance,
engineer the opening, resolve adjoining-wall corner ownership, or supply valley,
unequal-slope and multi-break cap joints. Retain those as project details.

## Verification

Run `tests/test_roof_layout.py` for independent roof area/intersection, coplanar
ownership, gap, parameter-change, original-blank, truss-representation and native
gable-wall checks. Existing roof-geometry and overhang tests cover detailed
stock cuts and the earlier tied-hip/gable recipes. Test the affected whole
building too: isolated geometry cannot establish its roof-to-wall bearings,
member spans, load path, overhang or stair-headroom compatibility.
