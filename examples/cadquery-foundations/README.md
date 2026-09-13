# Foundation composition studies

Initialize with `stud init /path/to/project --example foundations`. The default
design composes strip footings, stem walls, compacted fill, aggregate and a
separate slab. Change the imported builder in the copied `design.py` to another
function in the copied `foundations.py`. The project owns these recipes.

Available builders: `monolithic_slab`, `stem_wall_slab`, `crawlspace`, `basement`,
`walkout_basement`, `pier_and_beam`, `post_frame`, `mat_slab`, `pile_and_cap`,
`drilled_pier_and_grade_beam`, `helical_pile_and_beam`, `frost_protected_slab`,
and `rubble_trench`.

Each takes `model`, plus keyword arguments `object_id`, `width`, `length`,
`parent`, and `location`. Example defaults are inches and provisional dimensions;
the fixture plan dimensions must exceed 48 inches. Local grade is Z=0. All
builders preserve role-based part IDs when the plan changes. Nested rigid
placements also transform section planes, dimensions and bearing direction.

```python
import cadquery as cq
from stud.cad import Model
from foundations import basement, stem_wall_slab

model = Model('House and garage foundation study', units='in')
basement(model, object_id='house', width=240, length=192)
stem_wall_slab(model, object_id='garage', width=144, length=112,
               location=cq.Location(cq.Vector(264,0,0)))
```

This example deliberately leaves a gap between independent foundations. An
attached design needs an authored shared interface and transition details.

Shared geometry comes from `stud.solids.prism`, `round_member`, CadQuery
booleans/sweeps and existing `stud.stock` operations. Concrete, fill and aggregate
use `stud.bulk.volume_demand`; the quarter-yard delivery increment is a fixture
choice awaiting a supplier. Driven and helical piles are purchased as units.
Stock beams/posts retain their blank and cutting schedules. Insulation in the
FPSF study is a continuous envelope with explicitly missing panel layouts.

The studies include plan/section drawings, valid-solid and interference checks,
and selected explicit bearing contacts. A monolithic slab/edge is one fused pour;
a stem-wall garage floor remains a separate part. Helical piles include a pitched
helix and hollow shaft, but await a rated product's exact details.

These are geometry and purchasing examples, not complete construction packets.
They retain findings for site loads, soil, settlement, frost, groundwater,
reinforcement, joints, anchorage, durability and moisture/thermal detailing.
Raised-floor framing, reinforcement/anchors, pipes and membranes are not supplied
by these fixtures. Masonry, ICF, precast-panel and permanent-wood wall designs use
the same components with project-owned unit/stock details; consult the
[foundation authoring guide](../../skills/stud-design/references/foundations.md).
