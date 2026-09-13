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
`priority` and then stable ID; changing declaration order has no effect. Opposite
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
