# Composable hip roof

Run `stud init PATH --example hip-roof` to copy this study and its editable recipe
into a project. The default 12 × 8 ft footprint has four 6:12 roof planes and
8-inch horizontal eaves. It contains 83 physical parts: plates, ridge and posts,
backed hips, common/jack rafters, eave backing and cut roof sheets.

`hip_roof.py` owns the framing layout and joint choices. It uses
`stud.stock.Plane` for plane elevations, offsets and hip intersections;
`cut_member` for original stock frames, compound ends and hip backing;
`StockParts` for registration and grouped lumber demands; and the
`stud.roof_geometry.cut_panel` adapter for the four roof-plane sheet layouts.
The same generic operations power walls, floors and the existing gable helper.
No additional hip-specific engine interface is needed.

The default recipe declares 229 native requirements for valid solids, stock fit,
bearing, hip/jack/ridge contact, continuous deck-edge support and interference.
Its original blanks, individual board cuts and explicit 4 × 8 ft sheets reconcile
in the fabrication audit. Deck seams avoid the ridge/hip junction and land on
adjacent jack rafters. Run the checks and audit again after editing dimensions,
stock or layout; this example is not a general roof-layout solver.

This is a geometry and fabrication fixture. Member sizes and ridge-post supports
are provisional; foundation support, loads, bracing, uplift, notch limits and
connection schedules remain unresolved. Roof covering, fascia, soffits,
ventilation and weather closures are outside this example's scope.
