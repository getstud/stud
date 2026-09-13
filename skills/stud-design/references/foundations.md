# Foundations by composition

Use this reference for foundation selection, slabs, footings, below-grade walls,
piers, piles, frost protection and building-to-ground connections. Apply the site
intake in [Framed buildings](framed-buildings.md) first. For Stud development,
use labeled fixture criteria and missing-input scenarios.

## Define the assembly

Record three independent choices: support layout, wall/member construction, and
ground/thermal conditions. A basement can use poured concrete, masonry, ICF,
precast panels or a designed permanent wood system. Frost protection applies to
the selected assembly and its operating temperature. A floor slab may carry only
floor loads while separate footings and walls carry the building.

Use one project specification for plan boundaries, exterior grade, finished floor,
footing tops/bottoms, wall tops, bearing lines, column locations and penetrations.
Allow grade and footing elevations to vary by station for slopes, stepped
footings and walkouts. Declare the interfaces between an attached garage and
house, including changes in foundation depth, slab elevation and conditioned use.

## Shared components

| Component | Geometry and assembly meaning | Evidence and purchasing |
| --- | --- | --- |
| Bearing bed and earthwork | Excavation, compacted fill, aggregate beds or drainage trenches, each at an explicit elevation | Excavation versus installed compacted volume; soil suitability, compaction and any loose-volume conversion |
| Continuous member | Strip footing, grade beam, tie/strap beam, thickened slab edge, wall footing | Width/depth and support stations; bending/shear, reinforcement and bearing basis |
| Local spread support | Isolated, combined or eccentric pad; pile cap; pedestal | Contact faces, load eccentricity, punching shear and reinforcement |
| Wall or panel | Solid concrete wall, masonry units, precast panels, framed wood wall | Height, openings, joints, backfill height, earth pressure, top/bottom restraint |
| Slab or layer | Floor slab, structural mat, mud slab, aggregate, insulation, membrane | Physical outline, thickness, openings, slope, joints and independent purchasing basis |
| Shaft or post | Pier, drilled shaft, driven pile, helical-pile shaft, embedded timber post | Diameter/section, endpoints, embedment, bearing/shaft resistance, lateral and uplift restraint |
| Reinforcement and ties | Bars, bent cages, mesh, tendons, dowels, anchors, brackets and base plates | Cover, laps, bends, development, actual product capacities and connections |
| Water and thermal details | Drain pipes/outlets, waterproofing, capillary breaks, vapor/radon barriers, insulation and protection | Continuous routes/terminations, selected products, climate and groundwater criteria |

The geometry operations are material-independent. Use `stud.solids.prism` for
polygonal regions with through openings and oriented layers, and `round_member`
for solid or hollow round members. Use ordinary CadQuery for unions, edge
notches, tapered shafts, helixes and bent bar sweeps. Use `stud.stock` for wood,
stock panels and their cutting layouts; existing `Model` references, requirements,
connections and drawings supply their meaning. Read installed `docs/cadquery.md`
for signatures and bulk-volume demands.

Register one physical pour once: fuse intersecting slab/beam/edge regions before
registration. Separate pours meet at declared joints. Reinforcement and embedded
hardware may intentionally occupy the host concrete envelope; apply interference
checks to selected groups and check concrete cover separately. State whether
concrete takeoffs retain or deduct embedded steel/product displacement.

## Foundation families

| Family | Composition | Design details to resolve |
| --- | --- | --- |
| Monolithic slab / thickened edge | Slab fused with perimeter/interior thickenings over prepared base | Load-bearing lines, joints, edge bearing and frost strategy |
| Stem-wall slab / raised slab | Strip footings + short walls + interior fill/base + separate floor slab | Compaction, independent wall/slab support, floor/threshold elevations |
| Crawlspace | Strip footings + perimeter walls + local interior pads/piers + raised floor | Moisture liner, access, conditioned/vented strategy and floor connections |
| Full basement | Footings + retaining foundation walls + base/slab + interior pads/columns | Earth/water pressure, wall restraint, waterproofing and drainage |
| Walkout / stepped basement | Basement components with varying grade, stepped supports and openings | Retained grades, lintels, transitions, stair/door thresholds and discharge |
| Pier and beam | Individual pads/piers + beams + raised floor | Concentrated loads, bracing, uplift and beam/post connections |
| Post-frame / pole building | Bearing pads or selected post bases + embedded/anchored posts + frame | Embedment, decay/corrosion, backfill, lateral resistance and uplift |
| Mat / raft / ribbed raft | Structural slab + optional integral ribs/thickenings | Two-way behavior, punching, settlement and soil interaction |
| Piles and caps | Driven piles + individual/group caps + beams or supported slab | Pile selection, driving criteria, group effects, scour and lateral loads |
| Drilled shafts and grade beams | Cast shafts, optionally belled + caps/grade beams | Bore stability, groundwater, reinforcement and shaft/base resistance |
| Helical piles | Selected shaft/helix product + caps/brackets + beams | Rated capacity, installation torque/depth, buckling and corrosion |
| Frost-protected shallow | Shallow slab/footing assembly + designed vertical/wing/underfloor insulation | Heated/unheated design method, climate, soil drainage and corner details |
| Rubble / crushed-stone trench | Compacted stone trench + drain/filter system + grade beam or selected wall | Accepted design basis, drainage outlet, bearing and frost performance |

Combined/strap footings, sloping/stepped footings, grillages and mixed foundations
use the same components and explicit interfaces. A suspended slab is supported
by beams/walls/piles; its support and structural design differ from a ground slab.
An ordinary independent garage floor is not automatically a structural raft.

## Construction-system variants

- **Poured concrete:** model actual pours and joints; record mix, reinforcement,
  forms and curing/placement requirements. Use measured volume for concrete.
- **Masonry:** model selected units and course/bond/corner details, openings,
  mortar joints, reinforced/grouted cells and bond beams. Purchase blocks, mortar
  and grout separately; a wall envelope alone is not a verified block schedule.
- **ICF:** compose the concrete core, permanent forms, reinforcement and
  connectors. Use selected form geometry/yields, course layout and opening bucks.
  Count the purchased form system once, with its separate concrete demand.
- **Precast:** compose selected panels/piles/caps with seats, connections, joints
  and erection clearances. Purchase units by product rather than their envelope's
  volume of concrete. Hollow/ribbed panels need their actual section geometry.
- **Permanent wood:** use treated stock framing, structural sheathing, fasteners,
  the designed footing/base and moisture layers. Preserve treatment/grade and
  fastener compatibility; an ordinary above-grade framed wall does not establish
  below-grade suitability.
- **Post-tensioned concrete:** retain the slab/mat geometry and add the designed
  tendon paths, anchors and stressing details. Tendon layout, force and losses
  require their own design evidence.
- **Stone/masonry or timber piles:** retain the support layout but select the
  construction/product-specific sizing, connections, durability and purchasing.

## Author, check and deliver

1. Select the family and construction system from the intended building/site.
   Save load reactions, soil/frost/water criteria and the source of each resolved
   dimension; leave specific missing evidence visible.
2. Compose ground preparation, supports, walls/beams, slabs and the building
   interface from shared datums. Probe one pad/pier or footing/wall connection
   before replication. Add sections showing depth, bearing and material layers.
3. Check valid solids, intended contacts, support direction/area, opening and
   anchor clearances, cover and unintended overlaps. Soil contact in a CAD model
   establishes no bearing capacity; associate each supported load with its
   structural/geotechnical evidence separately.
4. Reconcile concrete/aggregate volumes, actual reinforcement lengths, purchased
   units and stock layouts. Model service trenches and drains if included in the
   scope; record excavation and disposal separately from installed materials.
5. Inspect the evaluated foundation with its wall/floor interfaces. Completion
   requires every requested component, quantity and connection to be accounted
   for, with unresolved site/product/structural items identified in the packet.

`stud init --example foundations` copies editable geometric studies for the 13
families above. See `engine/examples/cadquery-foundations/README.md` (checkout:
`examples/cadquery-foundations/README.md`). They demonstrate composition and
selected contact checks; system-specific construction details remain to be
authored for the actual project.

## Source basis

Use these sources for system understanding; select the adopted rules and current
product documentation for a project's numerical design. Reviewed 2026-09-12.

- [HUD Residential Structural Design Guide, second edition](https://www.huduser.gov/portal/publications/pdf/residential.pdf): foundation components, loads and connections.
- [PNNL basement assemblies](https://basc.pnnl.gov/resource-guides/air-sealed-insulated-basements): poured, ICF and precast construction with control layers.
- [PNNL open foundations](https://basc.pnnl.gov/resource-guides/flood-resistant-pier-pile-post-and-column-foundations): distinctions between shallow supports and deep foundations in flood conditions.
- [HUD FPSF guide](https://www.huduser.gov/publications/pdf/fpsfguide.pdf): insulation-based frost protection, including different heated/unheated design paths.
