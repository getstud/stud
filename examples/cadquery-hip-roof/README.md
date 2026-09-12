# Tied hip-roof framing example

Run `stud init PATH --example hip-roof` to copy the accepted framing study and
its editable `hip_roof.py` recipe into a project. The baseline is a 12 × 8 ft
footprint with four 6:12 roof planes and 8-inch horizontal eaves. It contains
69 physical parts, including the cut roof sheets.

## Framing rules

- Use a rectangular ridge board with low rafter ties. Cross ties run alongside
  paired rafters; segmented hip-end ties frame between them. There are no ridge
  posts. The 2x4 ties and their tension connections remain provisional.
- Extend the ridge half a member thickness beyond each ridge-end common
  centerline: 3/4 inch at each end here, for a 49-1/2-inch ridge. Keep its top
  square, set 3/8 inch below the theoretical peak so its edges clear the roof.
- Keep the hips square-edged, without backing bevels. Lower their axes by
  `thickness * slope / (2 * sqrt(2))`: about 0.265 inch here. Their outer top
  edges meet the roof planes; sheathing bridges the small center gap.
- At each ridge end, a full-width end common meets the ridge end, side commons
  meet the ridge faces, and hips meet the common-rafter corners. Include those
  common stations explicitly, replacing any overlapping grid stations.
- End **every** common with a plumb cut at its actual ridge face. End each jack
  with a side cut at the actual hip face. Subtracting a lowered support alone
  leaves a thin lip above it; explicit end planes remove the whole overrun.
  Keep the ridge-end commons separate from triangular jack-domain clipping.
- Retain footprint birdsmouth seats and plumb tails. Shorten tails by the
  subfascia thickness so the outside eave datum stays fixed.
- Use continuous vertical subfascia with beveled tops and mitered corners.
  Its inner depth is the plumb tail depth plus a 1/8-inch lower reveal, about
  6.27 inches here, ripped from 2x8 stock. The recipe selects deeper stock when
  necessary. This detail needs at least 1.5 inches of overhang.

## Geometry and validation

The project owns the arrangement; shared `stud.stock` plane/member operations
and `StockParts` preserve original blanks, cuts and purchase allocations.
`stud.roof_geometry.cut_panel` supplies the roof-plane sheet cuts. Deck seams
land on framing away from the ridge/hip junction.

The baseline declares 253 native requirements: 237 pass and 16 strict coplanar
panel-edge checks report findings. Those checks require opposing flat contact
faces, which do not describe the unbacked hip/ridge detail. Preserve these
findings; they do not establish sheathing edge or fastening adequacy. The
baseline has no solid collisions and its fabrication allocations reconcile.

`tests/test_hip_junctions.py` protects full-width junctions, square stock, direct
rafter contact, absent upper lips, plumb subfascia and low ties. The copied
example lifecycle is checked in `tests/test_example_projects.py`.

This is the accepted geometry baseline, not a general roof-layout solver.
Recheck all interfaces, mirrored tie stations and sheet seams after changing
footprint, pitch, spacing or stock. Loads, member sizing, notch limits, uplift,
wall/foundation support and every tie tension connection remain project design
work. Roof covering, finish fascia, soffits, ventilation and weather closures
are outside the example.
