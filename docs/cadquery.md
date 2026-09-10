# CadQuery projects

Current projects use `stud.json` with `engine: cadquery`, native project units (`in` or `mm`), and Python exporting `model`. Native CadQuery solids supply display geometry and measured evidence.

Choose units when creating the project: `stud init PATH` defaults to inches; `stud init PATH --units mm` creates a millimeter project. Units stay fixed across edits, checkpoints and options. Inch projects model a 1½-inch board as `1.5`, with an actual 2×4 section of `[1.5, 3.5]`. Metric projects use their actual millimeter dimensions; the same physical inch board would be exactly `[38.1, 88.9]`, not `[38, 89]`. Geometry is never automatically converted between project units. `Model(..., units='in')` declares units explicitly; omitting `units` inside a project inherits its declaration. Standalone Python models should declare their units explicitly.

Coordinates, stock sizes, bores, crops, tolerances and exploded offsets all use the project units. Length/area/volume checks report `in`, `in2`, `in3` or `mm`, `mm2`, `mm3`; mismatched explicit units are errors. BREP archives, meshes and placements retain native coordinates and carry their unit identity. The viewer uses an explicit camera/GPU presentation adapter while its labels retain the project units.

Imperial packets display exact sixteenth-inch fractions where possible and otherwise decimal inches to four places, with a four-inch calibration line. Metric packets use millimeters and a 100 mm line. A packet cannot switch the project's units. Physical paper margins remain explicitly named `margin_mm` because they describe paper, not model geometry.

## Runtime and request lifecycle

Source development requires Python 3.13, Git and Node.js. Create a virtual environment and install `requirements.lock` with `pip install --require-hashes -r requirements.lock`. Set `STUD_PYTHON` to that environment's interpreter when using the npm launcher. `stud doctor` reports the actual runtime and missing dependencies. Desktop preparation bundles checksum-pinned Python, Git and the locked CAD/PDF packages; see [desktop.md](desktop.md) for release gates.

Use `stud init PATH --example workbench` to create an independent project. Available fixtures also include `opening`, `roof-joint`, `shed` and `mansion`. Open `stud serve PATH --no-open` and use its printed URL. Read `stud status PATH`, then begin a request with its option head:

```sh
stud begin PATH --expected-head COMMIT --intent "Widen the workbench" --key unique-client-key
```

Edit the returned workspace, not the project's checkout. `stud source PATH --request REQUEST_ID` captures the exact declared source. `stud evaluate PATH --request REQUEST_ID --source SOURCE_ID --wait` evaluates it. File saves do not trigger builds. Complete a coherent set of edits, then evaluate explicitly; completed geometry still streams into the viewer during that build. Finish with `stud finish PATH --request REQUEST_ID --source SOURCE_ID --summary "Wider bench" --wait`; it requires a completed evaluation of that source, then freezes final source and records into one checkpoint. If `evaluation_required` is returned, evaluate the current source, wait and inspect its findings before retrying. Repeated requests/finishes are idempotent. A saved source error is reported as such and never borrows the previous build's estimate.

Status reads do not rebuild. `stud cancel` preserves the draft. Historical inspection and comparisons are read-only; they do not change an active request. Option activation requires finishing or canceling that writer. A restored design starts a new request and preserves current project-wide quotes and prompts.

## Registration and identity

Use ordinary CadQuery sketches, extrusions, booleans and assemblies. Register completed immutable shapes and project meaning:

```python
import cadquery as cq
from stud.cad import Model

model = Model('Shelf frame', units='in')
length = 30
model.assembly('shelf', 'Shelf frame')
model.part('shelf.front', cq.Workplane('XY').box(length, 1.5, 3.5, centered=(False, False, False)),
    parent='shelf', label='Front rail', material='lumber.1.5x3.5',
    blank={'size': [length, 1.5, 3.5], 'cut_length': length,
           'operations': [{'kind': 'square_cut', 'finished_length': length}]})
a = model.reference('shelf.front', 'start', point=(0, 0, 0))
b = model.reference('shelf.front', 'end', point=(length, 0, 0))
model.requirement('shelf.front.length', 'length', [a, b], threshold=length)
model.requirement('shelf.front.blank', 'stock_fit', ['shelf.front'])
model.dimension('shelf.front.length', a, b, label='Rail length')
model.drawing('shelf.front.view', dimensions=['shelf.front.length'])
model.demand('shelf.rails', product_id='lumber.1.5x3.5', specification={'section': [1.5, 3.5]},
    object_ids=['shelf.front'], unit='in', purchase_unit='board', stock_lengths=[96],
    cuts=[{'object_id': 'shelf.front', 'length': length}], kerf=.125)
model.step('shelf.prepare', 'Cut and label the front rail.', parts=['shelf.front'], view='shelf.front.view')
```

X/Y are horizontal, Z is up. Locations compose from parent assembly to part. Named point/axis/plane definitions use the part's local coordinates. The example is a single fabrication component; a complete shelf also needs its supporting parts and connections.

Object IDs identify authored physical parts across edits. Mesh shape keys identify cached immutable assets. Use physical station or role keys for repeated members; inserting a member must not rename unrelated ones. Register a replacement with `replace=True`; re-declare its named references. A batch publishes a coherent completed group and rolls back its metadata if the group fails.

The first completed geometry publishes immediately. A bounded writer coalesces subsequent previews so large designs do not serialize the entire model after every member. These previews contain completed geometry and named measurements; purchasing, checks, steps and drawings remain pending until their complete result is available. Finalization flushes the latest preview before retaining the full immutable result. A hard native crash preserves the last coherent geometry with interrupted-stage status.

`stud.json` declares source patterns and inputs. Frozen source excludes `records`, quotes, estimates, exports and session state. Runtime fingerprints include Python, all locked package versions, engine source, units and build settings. Retained native archives are queried only under a compatible runtime; historical meshes and saved estimates remain inspectable without re-executing them.

## Native geometric evidence

| Requirement | Targets | Threshold / measured units |
| --- | --- | --- |
| `length`, `point_distance` | Exactly two named points or coordinate triples | Distance equals threshold; length. |
| `solid_valid` | One or more part IDs | All native solids valid; boolean (threshold unused). |
| `stock_fit` | Exactly one part ID | Finished local solid outside its original rectangular blank is within tolerance; volume (threshold unused). |
| `collision` | Exactly two part IDs | Overlap volume at most threshold; volume. |
| `collision_free` | One or more part IDs, checking pairs within that group | Total overlap volume at most threshold; volume. |
| `distance`, `clearance` | Exactly two part IDs | Minimum native distance equals (`distance`) or is at least (`clearance`) threshold; length. |
| `contact` | Exactly two part IDs | Opposing planar contact area is nonzero and at least threshold; area. |
| `support` | Exactly two part IDs: supported part, bearing part | Projected opposing contact area is nonzero and at least threshold; area. Default bearing direction is world down. |
| `panel_edge_support` | Panel ID followed by one or more backing part IDs | Actual unbacked perimeter, including cutouts, at most threshold; length. |

Set meaningful thresholds and tolerances in project units. Requirements derive their length, area or volume units from the project; an explicit unit must match. `support` accepts `direction=[x,y,z]` in world coordinates. `panel_edge_support` requires `direction_local=[x,y,z]` toward its backing and names the panel followed by supporting parts. Nearby or side-only contact is not vertical bearing.

Length, area and volume units are `in`, `in2`, `in3` in inch projects and `mm`, `mm2`, `mm3` in metric projects. The query tolerance is a length: contact/support compare with its square, and stock/collision volume checks use its cube. Derive expected dimensions and areas from the shared design specification or stock frame, rather than display bounds that may include kernel padding. Correct the geometry or expected value when a check fails; preserve the intended tolerance.

This runnable geometric fixture demonstrates a panel fully backed by a block. It checks one interface before replication; it supplies no connection or structural-capacity evidence.

```python
import cadquery as cq
from stud.cad import Model

model = Model('Bearing interface probe', units='in')
length, width, base_height, panel_thickness = 12, 3.5, 1.5, .75
for part_id, height, z in [('base', base_height, 0),
                           ('panel', panel_thickness, base_height)]:
    model.part(part_id,
        cq.Workplane('XY').box(length, width, height, centered=(False, False, False)),
        location=cq.Location(cq.Vector(0, 0, z)),
        blank={'size': [length, width, height]})
    model.requirement(part_id + '.blank', 'stock_fit', [part_id])

model.requirement('panel.bearing', 'support', ['panel', 'base'],
    threshold=length * width, direction=[0, 0, -1])
model.requirement('panel.contact', 'contact', ['panel', 'base'],
    threshold=length * width)
model.requirement('panel.edges', 'panel_edge_support', ['panel', 'base'],
    threshold=0, direction_local=[0, 0, -1])
model.requirement('parts.interference', 'collision_free', ['panel', 'base'], threshold=0)
```

For a member bearing on several supports, declare a separate `support` requirement per pair with its own expected bearing area. `panel_edge_support` instead accepts multiple backing parts in one requirement. Preserve the original stock dimensions when cutting a part; finished cut dimensions do not redefine its purchasing blank.

Findings distinguish passed, failed, unresolved, unsupported and operation failures. Coverage is explicit; no requirements or uncovered parts do not imply a pass. Geometry availability is separate from checks and quantities. Structural analysis, automatic code compliance and a general constraint solver are outside this engine's scope.

Deterministic native queries can reuse exact evidence from `.stud/query_cache/`. Keys include native solid digests, applicable placements, query kind, targets, thresholds, policy, units, tolerance and the full runtime fingerprint. Stock-fit results use the local blank frame; neighboring support/contact queries include world placements. Corrupt or incompatible entries become cache misses. `stud evaluate PATH --request REQUEST_ID --source SOURCE_ID --full-checks --wait` repeats every native query; source Python executes fully in both modes. Price-only changes do not run CAD.

## Reusable construction

`stud.construction` supplies general stock-frame operations such as `cut_rafter`; `stud.buildings` supplies the composable `framed_wall`, `floor_frame` and `gable_roof` helpers. Specific designs—the workbench, rotated opening, roof-joint sample, shed and residence—live in their example projects. `stud init --example NAME` copies the design and its Python helpers into the new project so their geometry, fabrication choices and later edits belong to its captured source and history. They ship as editable examples, not construction API entry points.

The US framing helpers require an inch project and use actual imperial stock, 16-inch framing stations and 1/8-inch sheet joints. Metric construction uses project-owned functions with native millimeter geometry.

Walls generate individual plates/studs, opening framing, cut sheets, support references, stock demands and steps from one definition. Opening `x`, `sill`, `width` and `height` specify the clear rough opening. `exceptions` targets a persistent member key for an intentional bore. Missing exception targets fail instead of silently discarding the exception. Floor frames support explicit stair openings. Gable rafters retain true rectangular stock coordinates and measured birdsmouth seats; roof and gable sheets retain their physical cuts/backing.

Walls, floors and roofs accept a parent assembly and rigid local placement. Their drawing directions and dimension references follow the complete parent transform. `gable_roof(..., gable_ends=[...])` selects exterior gables when composing adjacent roof modules. The [courtyard residence workload](../examples/cadquery-mansion/README.md) exercises these placements and several levels of shared parameters in ordinary Python.

These helpers exercise detailed fabrication geometry. Read the authored notes and unresolved connections. The shed does not include site foundations, selected structural loads, roofing, flashing, cladding or installed door/window products. Use a project-owned CadQuery function for another construction method, with its own checks and fabrication data. [The shed example](../examples/cadquery-shed/README.md) describes its bounded scope.

## Purchasing and saved prices

Declare a demand's product, physical specification, purchase unit, pack size and contributing objects. Every dimensional field uses project units; demands and saved quotes retain `length_unit` as part of their purchase identity. The quote endpoint defaults an omitted unit to the project declaration and rejects a different explicit unit. Boards use concrete cuts, stock lengths and kerf. Panels use explicit stock sheets with panel offsets, sizes, cut operations and backing references. Purchased items use installed quantities and package yields. The fabrication audit reconciles physical objects, blanks, cuts, sections, panels and hardware before quantities can be complete.

Compatible demands pool before pack rounding. Different stock lengths become separate purchase lines. Cutting plans account for loss between cuts and before the reusable offcut. Allowances and quantity overrides live in `estimating.json`; they are separate from quote prices.

Saved quote records retain product/specification, purchase unit, currency, supplier, source, quote date, kind and project save sequence. Manual prices take precedence over sourced prices, then estimates; clearing a manual override exposes the next applicable record. Save sequence selects the latest quote within that precedence, independently of quote date. Explicit reconciliation is required for conflicting sequences.

Historical mode displays immutable original estimates. Common-price mode applies one saved quote basis to both designs' quantities and assumptions. Price edits use the coordinator records interface, without CAD execution. Missing quantities, missing prices and currency mismatches remain explicit; known subtotals are not complete totals.

## Drawings and packets

A drawing selects objects, direction/up vectors, dimensions, and optional section plane. `crop=[left,bottom,right,top]` crops the projected right/up plane without changing native geometry; `detail_of` links the parent drawing. Dimensions are measured on the native references before their model-to-sheet transform. A dimension outside its detail crop is a layout error.

Connections identify parts, instructions, hardware and unresolved evidence. Steps identify parts, connections, prerequisites, a drawing, and optional exploded offsets in world project units. Dangling references, cycles, missing cuts and uncovered parts remain packet findings. Drawings, stock, sheets and steps use consistent labels; the companion CSV retains every persistent object ID and mark.

The default compact layout combines related views and prints counted fabrication types instead of repeating instructions for every identical stud. C-labels map to every contributing object in `parts.csv` and the packet manifest; M-labels identify its material specification. Repeated board plans and sheet layouts state how many to cut. Choose `--layout expanded` or the Versions page's layout control for separate view/step pages. Both formats retain the same source and quantity evidence.

`stud plans PATH --checkpoint COMMIT --build BUILD_ID --wait` generates vector PDF, CSVs, SVG views and a manifest with exact source/build/checkpoint, price basis, print settings, file hashes and sheet transforms. Omitting a build locates compatible checkpoint evidence. Exports are immutable and survive later edits. Print at 100% and check the calibration line in the selected units. Software acceptance renders all pages; a usable construction packet additionally needs a reader to follow its actual details.

## Project ownership and recovery

Keep the full project folder, including `.git`, `.stud`, `records`, `checkpoints` and `exports`. A full-folder copy can rebase saved draft/artifact paths without changing the original project. Register the new path in the desktop catalog. A Git-only clone retains design and compact history; absent native artifacts require the recorded compatible runtime to reproduce.

Original prompt captures and quote records remain available across options and restoration. Deleted targets stay unresolved. Never edit immutable records or output files to correct a model; change the owning source or submit a new record through the coordinator.
