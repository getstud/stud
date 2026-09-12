# Roof types and detailing

Use this reference for roofs on framed buildings: houses, garages, workshops, additions, sheds and similar structures. Select the structural system and detailing for the building’s use, scale, loads and construction method. Read it when selecting or changing a roof, authoring framing or overhangs, or completing roof finishes. Read the common specification, the selected roof form, and the applicable shared details. Consistency means a complete, coordinated assembly for the user's choices; pitches, member sizes and overhangs remain project decisions.

## Common roof specification

Reuse saved answers. Establish the footprint and bearing lines; ridge/high-edge direction; pitch of each plane; wall-top elevations; eave and rake projections measured horizontally; roof covering; and open, lined or storage/loft interior intent. For broken or asymmetric roofs, also record ridge offset and break locations/elevations. A loft needs its own floor loading and support design.

Record the structural system separately from the shape: tied rafters with a ridge board, rafters on a supported structural ridge beam, single-span rafters/joists, or designed trusses. Identify bearing members, thrust restraint, uplift connections and the support path to the foundation. Apply the framed-building member-sizing process to each distinct member family. A roof-form label does not select sections or connections.

Derive one set of roof planes from these inputs. Use it for rafters, hips/valleys, gable infill, notches, sheathing, fascia and finish surfaces. Distinguish horizontal clear span, horizontal overhang and sloping cut length. Include actual ridge thickness and bearing datums when calculating cuts. Choose deliberate eave/rake treatment even for flush edges; a flush roof still needs a finished weather edge.

When using a reference drawing, retain its source and distinguish the illustrated span, pitch and stock from this project's inputs. Recalculate geometry and member selection for the current project. For example, the user-supplied Shedplans drawing depicts an 8×12 roof at 38°; those lengths and joint dimensions are not defaults for a 12×16 roof at 6:12. Check tie function from its position and connection design rather than inheriting a drawing's label.

## Gable

**Form and framing:** Two planes meet along a ridge with triangular end walls. Establish ridge direction and whether pitches/bearing elevations are equal. Generate common rafter pairs, the selected ridge system, required ties or truss webs, and gable-end framing as separate physical members.

**Overhang default:** Include projecting eaves and projecting gable rakes. Use gable-end soffit ladders: an inner attachment rail, repeated outriggers/rungs, and one outer fly rafter supporting the rake edge and soffit. Record separate eave and rake projections, actual ladder stock/spacing, attachment points and open/closed soffit treatment. Reuse accepted dimensions; otherwise propose proportions appropriate to the design and state the assumption. A flush edge is an explicit user/design exception, not the default. Derive rafter tails, ladder elevations, roof deck, fascia, soffits and corner returns together. Join the opposing ladder halves at the peak and coordinate the fascia/soffit peak cuts. Verify ladder attachment, peak contact, roof-plane alignment and supported soffit/deck edges.

**Details:** Fit gable studs to the end roof framing and selected tie arrangement. Provide defined attachment and lateral support at their ends. Where studs cross ties, choose a coordinated notch/offset and check remaining stock and connections; a horizontal member is not a reason to leave studs floating. Give blocking a specific purpose: bearing restraint, panel-edge support, or eave closure. Vent openings displace infill from the same opening definition.

**Finish and review:** Complete both eaves, both rakes, ridge closure and gable cladding. Verify birdsmouth seats, ridge contact, tie elevation and connections, gable support, and rake/soffit/corner-trim intersections. Use the ridge/tie and overhang guidance below.

## Shed / lean-to / mono-pitch

**Form and framing:** One plane runs from a high support to a low support. Record slope direction, high/low bearing elevations and the actual span between them. Use rafters or joists spanning those supports; model the high wall/beam and its bracing. An attached lean-to needs a documented connection to the existing structure; a visible ledger is not evidence of adequate anchorage.

**Details:** Define seats or hangers independently at each end. There is no paired-rafter ridge or collar-tie assembly. Coordinate sloping side-wall infill, high-edge termination and low-eave projection with the roof plane.

**Finish and review:** Drain toward the chosen low edge, with high-edge or roof-to-wall flashing where applicable, side verges and fascia/soffits. Verify both bearings, uplift path, high-wall stability evidence, runoff destination and the covering's permitted slope.

## Hip / pyramid

**Form and framing:** Roof planes slope toward every outside wall. A rectangular equal-pitch hip usually has a ridge; a square pyramid meets at an apex. Derive their locations from the actual planes. Model common rafters, diagonal hip members and jack rafters terminating at hips, or the specified truss system. Unequal pitches require recalculating hip lines and cuts.

**Details:** Size hip members and their supports for their own tributary loads. Derive jack lengths, side cuts and hip backing/drop from actual intersections. Resolve ridge/hip or apex connections and wall-corner bearing. A hip shape alone does not establish thrust restraint or wind adequacy.

**Finish and review:** Carry eaves, fascia, soffits and drainage around the perimeter; include hip and ridge finish closures. Inspect a corner, a jack-to-hip joint and the ridge/apex before repeating. Check bearing, plane alignment, panel support, support/load-path evidence and all corner returns.

### Accepted tied hip-roof recipe

For a conventional tied hip study, start from `stud init --example hip-roof`
and read its copied README and `hip_roof.py`. Preserve the accepted arrangement:

- Square ridge board with low cross ties and hip-end ties; every tension
  connection and member size needs project-specific evidence.
- Square-edged dropped hips and a lowered flat ridge top, set from the roof
  planes and actual thickness. The baseline extends the ridge half a member
  thickness beyond each ridge-end common centerline.
- Full-width end commons against ridge ends, side commons against ridge faces,
  and hips against their corners. Include mandatory commons without overlapping
  nearby grid rafters.
- Explicit plumb ridge-face cuts for all commons and hip-face side cuts for
  jacks. A boolean subtraction of a lowered support can leave an upper lip;
  inspect the full cut, including above the support. Apply triangular roof-domain
  cuts to jacks separately from the ridge-end common arrangement.
- Continuous plumb subfascia outside shortened tails, with beveled tops,
  mitered corners and depth tied to the plumb tail plus the selected reveal.

Use the example's junction regressions and native checks after edits. Keep
coplanar panel-edge findings visible for dropped square-edged framing: line
contact and a bridged seam are not validated by that face-contact rule.
The README owns the baseline dimensions, formulas and verification limits.

## Gambrel / barn

**Form and framing:** Each side has a steep lower plane and a shallower upper plane. Record both pitches and the slope-break position, plus desired interior clearance. Choose a designed gambrel truss or an explicitly supported rafter/beam arrangement before defining its members.

**Details:** Model the actual break joints, webs/chords, gussets or connectors and their support conditions. Two rafters touching at a change of pitch do not form a resolved structural joint. Loft floor members and loads are separate from roof ties unless the selected system explicitly combines those functions. Use the truss design's sections and connection schedule; arbitrary plywood gussets are not a substitute.

**Finish and review:** Fit end-wall studs and cladding through both slopes, with eave/rake finishes, ridge closure and a coordinated roofing transition at each break. Check break-joint geometry and design evidence, loft/headroom clearances, sheathing support and covering continuity.

## Saltbox / asymmetric gable

**Form and framing:** Two unequal roof sides meet at an offset ridge, often with differing wall heights or an extended rear slope. Solve each plane from its own run, pitch and bearing elevation; identify any intermediate support under the long side.

**Details:** Generate distinct rafter families and determine their support/thrust system. Verify that the two planes meet at the same ridge datum. A mirrored symmetric-gable cut list or tie layout does not cover unequal spans and reactions. An added lower roof segment also needs its attachment and flashing interface resolved.

**Finish and review:** Complete unequal gable profiles, each eave and rake, and drainage on both sides. Check each family's span/stock evidence, bearing seats, ridge interface and clearance; quantify each roof plane separately.

## Flat / low-slope

**Form and framing:** Select joists, beams or designed trusses, with a declared drainage fall. Record whether the slope comes from structure, tapered insulation or another supported buildup. Keep the structural plane and finished drainage surface distinct.

**Details:** Lay out bearing lines, roof openings and any parapets with their backing. Coordinate drains/scuppers or open-edge runoff and overflow provisions appropriate to the selected system. Check slope after accounting for the chosen buildup and relevant deflection/ponding design evidence.

**Finish and review:** Select a roofing system rated for the actual slope; model its edge/parapet/upstand terminations, penetration interfaces and drainage outlets. Verify that every drainage region reaches an outlet, that the buildup fits the framing, and that moisture/ventilation assumptions are recorded. A horizontal display slab is not a finished low-slope roof assembly.

## Other and compound forms

For mansard roofs, combine hip geometry with explicit lower/upper slope-break design; use the hip and gambrel joint reviews. For cross-gable, cross-hip, dormers and additions, derive valleys from intersecting planes, provide valley/jack framing and support evidence, and resolve concentrated runoff and roof-to-wall flashing. A butterfly roof needs explicit internal-valley drainage and overflow design. For curved or other requested forms, establish their geometry, supported structural system and covering detail instead of silently substituting a supported helper's shape.

## Shared framing and finish details

### Compose the recipe from shared geometry

Use `stud.stock` when it is available in the installed engine. `Plane.roof` establishes elevations from slopes; `intersection` derives ridge/hip/valley lines; `offset` locates neighboring member faces. `cut_member` preserves each original rectangular stock frame while clipping plumb or compound ends and backing faces. Generic `cut_panel` cuts a local profile in any CadQuery plane frame, and `StockParts` registers those member results with their grouped purchase cuts. Use `stud.roof_geometry.cut_panel` when the source outline is an XY roof footprint. Read `docs/cadquery.md` for coordinate conventions and signatures. Older installed engines may need equivalent project-owned CadQuery cuts until upgraded.

Keep roof selection and assembly policy in the recipe. The shared operations do not select a load path, stock sections, bearing seats, joint details, sheet subdivision or finishes. Register those physical parts, material demands and native interface checks in the owning project. Use the same planes for framing, deck and exterior finish datums.

| Form | Geometry composition |
| --- | --- |
| Gable | Two planes and their ridge; paired members with independent seats, gable infill, eave/rake members and panel footprints. Use `gable_roof` when its ridge/tie system fits. |
| Mono-pitch | One plane, two bearing lines and members cut to independent high/low support faces. |
| Hip / pyramid | Intersect adjacent planes for hips; choose dropped square-edged hips or a deliberate backing bevel; fit compound jack ends to finite hip/ridge solids; clip deck footprints to each plane's domain. |
| Gambrel / mansard | Distinct lower/upper planes and break lines; generate members for the selected supported or trussed break joint, then deck each segment. |
| Saltbox | Independent planes from each wall datum and pitch; solve their shared ridge and generate separate rafter families. |
| Low-slope | Structural support planes plus a separate drainage surface when the buildup creates the fall; retain the drain/edge openings in panel footprints. |
| Compound roofs | Intersect adjacent roof domains for valleys and ridges; use named support/connection assemblies at each junction and clip each panel footprint accordingly. |

Use `stud init PATH --example hip-roof` for the shipped four-plane composition study. Read its copied `hip_roof.py` and installed `engine/examples/cadquery-hip-roof/README.md` (checkout `examples/cadquery-hip-roof/`). It demonstrates dropped square-edged hips, compound jack ends, seat cuts, original blanks and panel cuts with explicit support findings; its member sizing, load path and finish scope remain provisional. Treat example dimensions as editable fixture inputs, and rerun checks after changes. Add shared geometry operations only when repeated recipe needs justify them.

### Overhangs and joint details

Verify the installed helper signature before use. Where available, `gable_roof` accepts `eave_overhang`, `rake_overhang`, `gable_finish_thickness` and `ladder_spacing`; its API defaults preserve existing flush models, so pass the chosen projections explicitly. Read installed `docs/cadquery.md` for the supported ranges and returned framing. Older app builds may lack these parameters: use project-owned geometry for the same declared detail, retaining the joint and finish checks below.

Keep the chosen form explicit. Use a supported builder or project-owned generator for that form; identify a missing capability instead of replacing a hip or gable with a flat roof. Distinguish structural ridge beams and their supports from ridge boards with the required tie system. A ridge board alone does not establish a stable roof.

For an open roof, seek useful overhead clearance and economical member lengths when selecting the tie arrangement. Distinguish each member's function: [American Wood Council guidance](https://awc.org/faq/what-is-the-difference-between-a-collar-tie-and-a-rafter-tie/) places collar ties in the upper third to resist separation near the ridge under uplift, and rafter ties in the lower third to resist outward gravity thrust. High collar ties do not replace required lower rafter ties. Ceiling joists can also serve as rafter ties only with suitable continuity and connections.

Where more clearance is needed, consider a supported structural ridge system or a specifically designed raised-rafter-tie arrangement, together with the applicable collar-tie/ridge-connection detail. Establish tie elevation, spacing, section, connection basis and clear height from the selected system before generating it. Compare total material quantities, including ridge supports and connections, before claiming savings. The current `gable_roof` ridge-board builder generates plate-level rafter ties; use a supported alternative or project-owned generator for raised ties, and keep unresolved structural evidence explicit. Moving those existing ties upward or relabeling them as collar ties is not a complete system change.

For sawn rafters with birdsmouths, derive seat and heel cuts from plate position, pitch and required bearing. Keep each cut rafter one physical part with its original stock blank. Check actual seat contact and the sourced notch/remaining-section limits. Engineered rafters/trusses follow their manufacturer's permitted cuts and connections.

Derive eaves, rakes, tails/lookouts, fascia, soffits and roof skins from shared roof planes and finish thicknesses. Choose open or closed overhangs, the rake support arrangement, fascia proportions and corner-return treatment for this design. Use the installed helper’s supported overhang parameters for framing and project-owned assemblies for finishes, with named interface checks.

When using a ladder rake detail, its single outer fly rafter and inner attachment rail meet the selected fascia, soffit and main framing. Check the connections, panel edges and peak closure. A triangular bird-box face follows from matching eave fascia depth to the plumb rafter tail plus rake-soffit overlap; deeper fascia produces a different closure. Return length and separate fascia grouping are project choices. An extended ridge needs a coordinated enclosure; a structural ridge beam also needs its support/connection design.

For a new gable shed, consult `engine/examples/cadquery-shed/README.md`, `design.py` and `shed.py` (checkout `examples/cadquery-shed/`). Use `stud init --example shed` to copy the model into its own project. This example covers framing and sheathing; it does not supply a complete foundation, exterior enclosure, roof finish or installed opening products. Adapt its geometry and recheck changed interfaces.

For asphalt roofing, author the selected system in project-owned CadQuery code.
Record product stock yields and representation limits. Include deck, membrane/ice protection, eave/rake drip
edges, starters, field shingles and ridge closure; account for roofing dead load.
Check deck-to-rafter bearing, required panel edge support and finish substrate
contact before covering. Bevel fascia tops to the roof plane. Retrieve the
selected manufacturers' current slope, exposure, overlap, fastening and edge
instructions. Establish ventilation and condensation control with the end user
when designing a real building. For tool-development fixtures, record those
inputs as provisional rather than requesting a development user's site.
Exposed-coverage graphics do not model concealed laps or prove weather sealing;
keep those limits explicit. Count shingles by installed coverage and ridge/edge
accessories by length, including package yields and cutting/lap allowances.

## Completion of the roof stage

Review one representative bearing joint and every unique ridge, hip, valley, slope break and roof-to-wall intersection. Then account for all selected roof planes, member families, required ties/bracing, deck edges, eaves/rakes, fascia/soffits, cladding/trim closures and roofing transitions. Declare named native checks for the measurable interfaces; account for stock cuts and purchases by family. Classify structural, fastening and product evidence separately from geometric findings. Complete a conceptual model with specific unresolved items when appropriate; do not describe it as ready for fabrication on the strength of geometry checks.

## Sources and limits

Primary references checked 2026-09-11; consult the applicable edition and selected products for project decisions:

- [American Wood Council framing FAQs](https://awc.org/about/frequently-asked-questions/) distinguish ridge beams, ridge boards, rafter ties and collar ties. Use the selected system's design provisions when changing tie height.
- [PNNL: Hip Roof vs Gable Roof](https://basc.pnnl.gov/resource-guides/hip-roof-vs-gable-roof) discusses the forms and wind behavior; roof shape does not replace connection and bracing design.
- [SBCA: Building Component Safety Information](https://www.sbcacomponents.com/bcsi) covers truss restraint and bracing. Use project truss design drawings for member and joint specifications.
- [APA: Moisture Mitigation](https://www.apawood.org/applications-systems/design-guidance/moisture-mitigation/) links guidance for moisture control, including low-slope roof systems.

The [user-supplied Shedplans tutorial](https://shedplans.org/shed-roof-framing/) is a visual reference for its particular shed, not a universal sizing or connection specification. The roof-form sections above are authoring and review guidance; they do not supply prescriptive member schedules.
