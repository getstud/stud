# Composable floor fixture

Create an independent copy with `stud init PATH --example floor-system`.
The installed `stud.framing` and `stud.floors` modules own layout, solid/I stock,
opening framing, hardware envelopes, purchasing records and native checks.
The copied `design.py` owns dimensions, products, support choices and openings.

Change `OPENINGS` to move or resize the stair void; change `JOIST` to use a
solid member profile. Re-execution rebuilds the affected members and quantities.
`INCLUDE_DECK` adds an independent sheet operation using the same openings.
Compose another `frame_floor` with its own placement and bearing interfaces for
a wing with a different joist direction. See [floor systems](../../docs/floor-systems.md).

This is a generic geometric fixture. Support bodies, stock and connection
dimensions are provisional. Recorded design gaps remain visible even when the
native geometry passes. No private building plan is included.
