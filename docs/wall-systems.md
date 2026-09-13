# Connected wall framing

Author named `WallLine` edges and `WallRun` specifications in project Python.
`outside`, `center` and `inside` alignment place actual wall stock relative to an
edge. `run.face('inside')` provides a derived line for a dependent wall. Rebuild
these specifications on every execution so edited datums flow through the model.
Drawings are optional evidence and are never required by this interface.

`stud.wall_layout.layout_walls(runs)` returns immutable value records for the
connected layout before any parts are registered. Planar junction masks use OCCT;
finished member solids, stock purchases and native checks belong to the subsequent
framing operation. The returned records contain polygons, not mutable CAD shapes.

Each shared wall is authored once. Junction ownership sorts by explicit run
`priority`, descending run length, and then stable ID; changing declaration order has no effect. Opposite
ownership in the second top course produces laps. Unequal base/top elevations do
not get an invented plate lap. Overlapping runs with different bases require a
split junction. Footprints can describe angled ends within the stock strip.

Openings specify rough-opening `station`, `width`, `height`, and `sill`. Optional
`unit_size` and `clear_size` preserve their different meanings. Openings stay fixed
unless `max_shift` explicitly permits movement. The result reports every adjustment;
a conflicting fixed opening fails before registering parts. For several movable
openings, placement proceeds in station/ID order; this is a bounded local fit,
not a global optimization search. If that fit is impossible, revise the input.

The geometry does not select code requirements, structural capacity or products.
Corner backing, fastening and sizing evidence must accompany the chosen details.

## Physical members and checks

```python
from stud.wall_layout import WallLine, WallRun, WallOpening
from stud.walls import HeaderDetail, OpeningDetail, frame_walls

# All values below are inches in this example; model units govern all inputs.
edge = WallLine('deck.south', (0, 0), (120, 0), base=12)
opening = WallOpening('entry', station=40, width=32, height=80,
                      detail=OpeningDetail(HeaderDetail(depth=9.25)))
wall = WallRun('south', edge, height=96, depth=5.5, openings=(opening,))
framing = frame_walls(model, [wall], floor_supports=deck['panels'])
```

`plan_wall_members(layout_walls(runs))` returns cut profiles, original stock
frames, stable member IDs, expected inventory and geometry issues. `frame_walls`
accepts either the inputs or this plan. The adapter extrudes planned profiles,
registers stock purchases and native requirements, and returns member mappings.
The owning Python specifications regenerate dependencies on each execution.

Opening details compose `HeaderDetail` (individual plies, jack count and optional
cap), `PocketDetail` (pocket envelope and separate base/stud stock families), and
`TransomDetail` (supported intermediate rail and upper sill). These dimensions are
explicit geometric selections, not structural sizing. The header and each end
seat are checked independently. Cap bearing follows the selected ply positions.

Plate stock is segmented within the selected cut limit on the stud grid, with
an explicit second-course splice offset. A splice centered on a stud uses its
planned half-stud seat on each side. Incompatible stock/grid/offset combinations
fail planning. Angled-end projections are checked at the planned full-section
seats and retain a specific connection detail requiring load-transfer review. Field studs keep station IDs and fit complete sections at angled
ends. No frame-wide screw schedule is invented: unresolved product, fastening,
load transfer and bracing evidence stays on its owning connections.

A deliberately shared bay/corner opening may set `shared_jambs=True`. Its fixed
station must still fit the directed run, but the ordinary junction clearance is
replaced by an explicit geometry finding requiring a shared-post detail. This is
an exception record, not a complete shared-jamb construction solution. Missing
jambs remain expected inventory; inadequate clipped sections cannot be reported
as verified geometry. `corner_backing='clips'` likewise records a selected backing
approach with a pending clip schedule; it does not invent physical hardware.

Bottom plates and ordinary vertical members require their planned cut-footprint
area in downward contact. Cripples directly over an uncapped built-up header
instead require the contact strips of each authored ply, checked separately. Several floor panels can jointly supply it: `support` measures
the union of their real solids, preventing double counting. Removing or shortening
a support invalidates that check. Missing seats and thin remnants are geometry
findings, while load capacity and hardware selections remain construction details.
Inspect `design_review` together with native check results.

For a migration, optional `id_aliases` maps planned member IDs to existing full
part IDs. It preserves review references without turning list indices into the
new layout's identity scheme. Keep migration mappings and building-specific
set-out in the private project, not in Stud's installed examples.
