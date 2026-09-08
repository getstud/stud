# Construction assemblies

Stud provides transactional floor, wall, gable-roof and opening-unit builders. All dimensions are actual inches. They add geometry and named requirements together; removing a member or its rule cannot silently erase the requirement. Their results expose `roles`, `part_ids`, `frame` and builder-specific `interfaces`. Invalid inputs leave the destination project unchanged.

These are geometric construction tools. Member sizing, connection capacity, site conditions, product instructions and adopted requirements remain project inputs. Read the generated unverified findings before treating an assembly as complete.

## Floor

```python
from stud import floor_frame
floor = floor_frame(project, 'floor', width=144, depth=192,
    joist_stock='joist', panel_stock='subfloor',
    support_ids=['beam.west', 'beam.east'])
```

The default runs joists across the shorter outside dimension, with the rim thickness deducted from their clear length. Plan support lines first: this geometric default cannot infer an unsupported span from arbitrary beams. `joist_axis=0|1` chooses local U or V; overriding the default requires `direction_reason`.

Rims provide end restraint. `blocking_rows` are distances along the member run. `maximum_block_spacing` requires a `blocking_basis`, and checks actual row positions and end restraints. It is never an automatic code interval. The builder models rectangular sawn members; it does not model an engineered I-joist or interpret its manufacturer's details.

Panels put their long dimension across joists. `panel_edges='blocked'` adds seam backing; `'tongue_and_groove'` requires `panel_joint_basis`, checks coplanar adjacent joints and retains boundary/end support. Sheet ends must align with joist centers. Each `support_ids` member is a declared bearing line under every joist; omit it only when leaving bearing explicitly unverified.

## Walls and enclosure

```python
from stud import WallFrame, wall_frame, wall_enclosure
walls = wall_frame(project, 'walls', width=144, depth=192, height=96,
    stud_stock='stud', header_stock='header', spacer_stock='sheathing',
    frame=WallFrame((0, 0, floor.interfaces['top_elevation'])),
    support_ids=[pid for role, pid in floor.roles.items() if role.startswith('panel.')],
    interior_finish=True,
    openings=[dict(id='entry', wall='front', start=50, width=38,
                   bottom=0, height=82)])
skin = wall_enclosure(project, 'skin', walls=walls,
    sheathing_stock='sheathing', siding_stock='siding', trim_stock='trim',
    liner_stock='liner', trim_gap=.125)
```

Width/depth are outside framing, height includes the bottom and two top plates. `front`/`back` run U, `west`/`east` run V. Frames support arbitrary horizontal rotation and mirrored depth. Opening starts are measured in each wall's own frame, available at `walls.interfaces['walls'][name].frame`.

Supply `support_ids` with the floor panels or other actual bearing parts. Every bottom-plate segment then requires full-footprint downward contact with their union; an empty scope remains explicitly unverified. Removing a support or separating the floor is detected independently of internal wall checks. Bearing does not establish attachment or load capacity. Bottom plate IDs are available as `walls.interfaces['bottoms']`.

Caps overlap corners. Long stock runs split with staggered top-plate joints (24 inches by default), and actual splice positions are checked. `plate_junction` creates a separate L/T plate detail using `main_length`, `branch_length`, `branch_at` and `stock`; host stud framing is separate.

`interior_finish=True` creates three-stud corner backing. It is required when requesting a liner. Clips and alternative plate connections are project-authored details, not built-in alternatives. Liner edge support, stud foot/head contact, cap laps, exterior trim joints and siding-to-sheathing contact are measured. Exterior sheathing attachment, panel bracing, WRB and flashing remain explicit unfinished work.

Enclosure uses two vertical butted boards per corner. Siding terminates at the selected `trim_gap`; that dimension is an installation input, not an accidental gap to remove. All opening cuts share the host framing's clearances. `exterior_height` can terminate skins and corner boards at a soffit/infill datum while the liner remains full height. It must cover every opening; upper weather closure remains explicitly unverified. For a roof from the same project use `roof.interfaces['soffit_bottom'] - walls.frame.origin[2]`. Plan this interface before adding the skins.

## Roof

```python
from stud import gable_roof
roof = gable_roof(project, 'roof', length=192, span=144, pitch=6,
    plate_depth=3.5, frame=WallFrame((144, 0, 104), 90),
    rafter_stock='rafter', ridge_stock='ridge', tie_stock='stud',
    system='ridge_board_ties', plate_ids=(east_caps, west_caps),
    maximum_notch=2, minimum_remaining=5,
    notch_basis='Regression values only; replace with approved design limits',
    eave_overhang=12, rake_overhang=12, fascia_stock='fascia',
    soffit_stock='soffit', bird_box_stock='bird_box_closure',
    soffit_support_stock='nailer',
    soffit_wall_ids=(east_wall_framing, west_wall_framing))
```

Local U follows the ridge; local V spans outside wall faces. Frame Z is the top of the bearing plates. Pitch is rise per 12 inches. `plate_ids` contains the actual caps for each eave wall. The example notch limits are fixture inputs, not construction recommendations.

`sawn_rafter` generates a single polygon-extruded stock blank with a real seat, heel and plumb end cuts. Both viewer and measured validation use that profile; stock and CSV exports retain one member. Seat contact and notch depth/remaining normal stock section have named checks. Legacy box-only rules report unsupported outline geometry as unverified.

Choose `ridge_board_ties` with tie stock, or `structural_ridge` with separately designed `ridge_support_ids`. A missing ridge support remains unverified. Gable is the initial built-in form; do not substitute it for a requested hip or shed roof.

Eave overhang may be zero. Fascia follows tail cuts; optional eave soffits require fascia and separate 2× dimensional support stock (actual 1.5-inch thickness, at least 3.5-inch depth). Ledgers and soffit joists stand on edge. Named section checks detect undersized or flattened framing. Stock must fit the fascia drop and soffit depth; a deeper section may require deeper fascia and a lower soffit datum. Supply `soffit_wall_ids` for both eave walls, using their actual framing part IDs. Ledgers meet the outside framing plane; soffit panels extend to that plane above the wall finishes. The earlier `wall_finish_depth` argument was removed because it displaced the ledger from its framing. Ledger-to-wall and cross-member connections have named contact requirements. Empty host scopes are rejected. Contact establishes a geometric connection only; fasteners, spacing and capacity still need the selected detail. Rake overhang adds a single full-depth outer fly rafter and an inner ladder rail against the main end rafter, doubling only the attachment at the main roof framing. Both rails and the ladder lookouts use `rafter_stock`, with separate fascia outside the framing. Rake width must exceed two rafter thicknesses to fit both rails and the lookouts. When `soffit_stock` and its supports are supplied, the builder also creates sloped rake soffits, continuous inner edge backing, cross backing at panel ends/seams, and bird-box returns at all four eave corners. The closed detail requires an eave overhang at least the rafter depth times the sine of the roof angle to fit the first sloping cross-member. Invalid combinations fail transactionally.

Bird boxes have flat soffit bases at the eave datum, plumb back closures, slope-cut outer infill and 2× edge blocking. Rake fascia is cut to the rafter depth plus the soffit thickness (rafter depth alone for an open rake), independently of the deeper eave fascia. `rake_fascia_stock` may provide a narrower purchase blank; its thickness must match the eave board and its width must fit the cut. The original blank stays in the takeoff. Named upper/lower face checks enforce the cut width. Closure sheets use the eave fascia thickness for flush butt joints; the base uses `soffit_thickness`. Use `bird_box_stock` for the face/back closures and `soffit_stock` for the bases and sloping/horizontal soffits. Register different thicknesses as separate stock IDs with `sheet_thickness`; automatic stock-fit checks then reject a mismatched blank. Omission retains the legacy shared stock, so a different closure thickness needs an explicit separate stock to produce a usable purchasing row. The eave fascia ends at the outside rake face; a separate bird-box face fills beneath the slimmer rake board down to the eave-soffit datum. Named contact and projected-alignment checks verify the fascia corners and peak, doubled rafters, soffit attachments and bird-box edge support. Sheet-length limits split rake soffits and add seam backing. Roof sheathing/covering, vents and weather-edge details remain separate work, reported explicitly. Roof-aware wall enclosure supplies gable cladding. Attachment and load capacity are not inferred from contact.

## Door and window products

```python
from stud import door_unit
project.stock('door', 'Selected prehung door', '#b57b51',
              product=True, purchase_unit='unit')
project.stock('sill_packer', '½ in sill packer', '#b99466',
              sheet=(48, 96), sheet_thickness=.5)
opening = walls.interfaces['openings']['entry']['opening']
unit = door_unit(project, 'entry.unit', opening=opening,
    product_stock='door', frame_depth=5.125, inset=-1.125,
    hand='left', swing='in', obstacle_ids=walls.part_ids + skin.part_ids,
    sill_support_stock='sill_packer',
    sill_support_ids=[pid for role, pid in floor.roles.items() if role.startswith('panel.')])
```

The product frame must span the host framing depth. Negative `inset` extends toward the exterior; choose depth/reveals using both finished-wall planes. Installation clearance is separate from the usable opening. Doors include jambs, head, threshold, leaf and selected swing states. Left/right means minimum/maximum local U, and inward means positive local V.

`window_unit` supports fixed, outward casement and two-track slider operation, including rails, sill and transparent glazing. Pass surrounding framing, finishes and other obstacles explicitly. Clearance checks sample states, not a continuous swept volume; the viewer displays the closed product. Hardware, flashing, trim connections and manufacturer net clear opening remain unverified.

`sill_support_stock` and `sill_support_ids` optionally add a continuous installation packer below a door or window, filling the positive installation gap across the unit width and host wall depth. Both the packer-to-host and sill/jamb-to-packer bearing have named checks. Window host support normally names the rough-opening sill. Missing support inputs remain unverified; unknown parts or invalid stock fail transactionally. Packers count as installation material, separate from the purchased product. This detail leaves projecting sill/threshold noses, material suitability, fasteners and pan flashing subject to the selected manufacturer detail.

Register product stocks with `product=True`; one builder ID is one purchase, regardless of visual subpart count. Products cannot simultaneously declare lumber, sheet or coverage stock. Two units using the same stock count twice. Pricing uses the product's `purchase_unit`.

## Distribution and verification

Desktop preparation copies the complete source skill, its references and modeling documentation, then verifies inventory and bytes. Verify a prepared or installed Resources folder with:

```sh
node scripts/design-resources.mjs verify /path/to/Stud.app/Contents/Resources
```

A source change does not update an already installed app. Use the checkout CLI to exercise these APIs until a new desktop package is installed. Behavioral fixtures live in `tests/test_construction_assemblies.py`, `test_roof_assemblies.py`, `test_opening_units.py` and the Python/JavaScript profile tests.

## Gable end uprights

`gable_end_frame(project, 'gable', roof=roof, stud_stock='stud', plate_ids=(front_caps, back_caps), spacing=16)` adds actual 1.5 × 3.5-inch uprights from the end-wall caps to the roof slope. Pass the upper cap IDs in the roof frame's start/end order. Uprights are single stock blanks with slope-cut heads, depth notches around the end rafters and bottom rebates around end ties. A center upright meets the ridge underside; field studs avoid its actual footprint. Named requirements check cap bearing, rafter shoulders and heads, ridge contact and tie rebates. Rotated and mirrored roof frames are supported.

This detail requires enough height for each notch to retain a connected section; incompatible low slopes or member combinations are rejected transactionally. It does not infer arbitrary cuts around unrelated parts. Notch strength, fastening and bracing remain explicitly unverified. Gable skins/weather closure remain separate enclosure work.

## Rafter sizing from published tables

`select_rafter_size` returns the smallest **listed** section for the supplied horizontal clear span. The initial bundled table is [SFPA Maximum Spans, 2013 edition, Table 23](https://www.southernpine.com/wp-content/uploads/2023/11/SPtable23_060113.pdf), Southern Pine No.2, dry service, 40 psf adjusted roof snow plus 15 psf dead load, L/240, uniform loading and supported/braced top edges. It contains 2×6 through 2×12 at 12, 16, 19.2 and 24-inch spacing. It does not establish whether 2×4 would work. Unsupported conditions and spans beyond the listed sections raise `ValueError`; no species substitution, load substitution or interpolation occurs.

```python
from stud import select_rafter_size
# Illustrative lookup inputs, not site defaults. Establish loads from the site.
conditions = dict(species='Southern Pine', grade='No.2',
    roof_snow_psf=40, dead_load_psf=15, deflection_limit=240,
    service='dry', top_edge_braced=True, uniform_load=True,
    load_basis='Replace with the project-specific roof-load source')
sizing = select_rafter_size(span=72, spacing=16, **conditions)
# sizing['nominal'] == '2x6'; sizing['allowable_span'] == 114 inches
project.stock('rafters', sizing['nominal'], '#bb965f',
    section=sizing['section'], lengths=(96, 120, 144))
# Pass span_table=conditions and rafter_stock='rafters' to gable_roof.
```

The gable builder derives clear horizontal span from its ridge face and plate's inside face. It checks stock against the selected section, verifies actual bays stay within the table spacing, and requires at least three rafter pairs. The lookup record is exported on each main rafter and returned in `interfaces['rafter_sizing']`. Existing callers without `span_table` remain supported with an explicit `rafter_sizing` unverified finding. This makes a manually selected size visible as provisional.

Selection establishes a span-table candidate, not whole-roof adequacy. Notch depth/remaining section, bearing capacity, overhang loading, ridge supports, bracing installation, uplift and connections remain separate checks. A failed notch/detail can require a different bearing detail or a separately justified larger member; it is not permission to relax limits. Raised ties and other load patterns require an applicable design basis outside this lookup. Other member families and table conditions use the documented source-based planning workflow until their tables are implemented.


## Continuous gable cladding and corner trim

Pass `roof=roof` to `wall_enclosure` for a closed gable roof whose ridge runs between the front/back walls. It derives the eave-wall finish height from the roof soffit; a conflicting `exterior_height` is rejected. Roof span, run, orientation and wall-top datum must agree. Front/back upper sheathing and siding are cut to the sloping soffit and around the ridge underside, with full-footprint siding-to-sheathing checks. Existing lower panel IDs remain stable. Set `exterior_bottom` to a negative wall-base offset when the finish must also cover the floor rim; interior lining and opening datums remain at the wall base.

Declare shared trim dimensions before building either assembly. With 1/2-inch sheathing and actual 3/4 × 3-1/2-inch corner boards, supply `corner_trim_clearance={'projection': 1.25, 'side_run': 2.25}` to `gable_roof`. Projection equals sheathing plus trim thickness; side run equals trim face width minus that projection. The enclosure verifies that its dimensions match. These inputs notch the eave and bird-box soffit panels, add edge backing, and scribe the bird-box backing around the trim. The supported detail requires projection no greater than the 1.5-inch soffit framing thickness, enough panel length for backing, and a bird-box back thickness between the sheathing thickness and trim projection. Unsupported combinations are rejected.

Corner trim extends above the horizontal bird-box base to the gable-soffit region. Front boards receive an edge cut around the return; side boards have connected depth cuts around the ledger and bird-box back. Each remains one stock blank and one cut-list entry. Upper trim receives named backing-contact requirements. Scribed depths and fasteners still need the selected construction detail; these checks establish fit and support contact.

`Project.layered_prism` represents such a connected physical blank using `profile.layers`, each with an `x` interval and one or more nonoverlapping Y/Z `outlines`. Layers partition the blank thickness; their retained sections must form a connected member. Invalid, overlapping, detached or out-of-blank cuts fail before mutation. The viewer renders the exposed boundary, omitting internal faces between layers. `panel_support` checks the complete polygon perimeter for constant-thickness outline panels, including the new trim notches.

### Asphalt roof finish

`asphalt_roof(project, id, roof=roof, deck_stock=..., membrane_stock=...,
shingle_stock=..., flashing_stock=..., starter_stock=..., cap_stock=...)` follows
an existing `gable_roof` at pitch 4:12 or greater. It generates 5/8-inch deck
panels by default, a membrane envelope, visible drip-edge aprons, eave/rake
starters, staggered charcoal-style shingle coverage and a closed ridge cap.
The eave fascia is beveled to the same roof plane. Deck panel long edges run
across rafters and end seams use rafter stations. Panel edge blocking/clips,
installation gaps, staggering, fastening and span rating remain explicit
unverified requirements; contact checks alone do not approve a deck schedule.

Deck stock needs `sheet` and matching `sheet_thickness`. Membrane and field
shingles need `coverage_sq_ft` as installed net yield. Edge metal, starters and
ridge caps need `coverage_linear_ft` and `purchase_unit`; their generated parts
carry `coverage_length_in`. Split ridge faces together count one ridge length.
Linear takeoff applies the stock's waste allowance and rounds to purchase units.
It rejects missing, negative or nonfinite length metadata. Fixture accessory
package yields are provisional inputs; verify selected products before ordering.

The finish uses exposed-coverage solids. Hidden headlaps, folded metal roof
flanges and membrane laps are installation requirements, not fabricated geometry.
This keeps field-shingle yield separate from concealed material. Thicknesses
are assembly envelopes. Defaults use 5 5/8-inch exposure, 6-inch course offsets
and 1/2-inch edge projection, with reference to [GAF LayerLock instructions](https://www.gaf.com/en-us/document-library/documents/installation-instructions-&-guides/timberline-layerlock-installation-instructions-trilingual-restl622.pdf).
Those instructions distinguish eave metal beneath membrane and rake metal
above it. This builder rejects low-slope roofs requiring a different membrane
detail. A closed cap is not a ventilation design. No penetrations or valleys are
included. Record roofing dead load, ventilation/condensation strategy, ice-barrier
extent and selected fastening/sealing instructions before construction approval.

### Exterior opening trim

Pass `opening_trim_stock`, `opening_trim_width=4` and
`opening_trim_overlap=.5` to `wall_enclosure` to add casing. Width is the actual
finished face, in inches. The stock may be wider: the builder keeps each ripped
board's original blank for purchasing. The fixture uses 3/4 × 5-1/2-inch blanks
ripped to a 4-inch face, matching the existing cream trim.

Openings at floor level receive two jamb boards and a full-width head; raised
openings also receive a bottom board. The overlap extends into the rough
opening and must match the unit's installation gap. Include enclosure part IDs
in the unit's obstacle scope to check operation against the casing. Siding cuts
include `trim_gap`, including gable siding when a door head crosses the soffit
band. Sheathing remains behind the trim. Checks cover backing contact, finished
face width, butt joints and member presence. Trim that conflicts with corners,
another surround or the roof profile is rejected. Flashing, sealant, fastening
and product-specific sill details remain part of the enclosure installation.

For a door above an exposed floor rim, supply `door_kickboard_stock` with
`exterior_bottom < 0` and opening trim enabled. The kickboard replaces siding
below the door, spans the full casing width, and matches casing thickness. Its
finished height follows the floor-rim exposure; its wider purchase blank is
retained. Backing and both casing joints are checked.

### Closed gable peak and ridge termination

`gable_roof(ridge_termination=None)` selects `wall` for a ridge-board/tie roof
with rake overhangs and soffits. In that detail, the full-depth ridge stays
between the gable-wall planes. Single outer fly rafters and inner rake backing meet
at the centerline, with ladder blocking supporting soffit panels through the
peak. The corresponding `wall_enclosure(roof=...)` closes the cladding without
an exposed-ridge notch. Named checks constrain the ridge envelope and require
fly-rafter, backing and soffit peak contact. Connection capacity and the selected
peak strap/angle fastening schedule remain explicit requirements.

`ridge_termination='extended'` retains the alternate extended-ridge geometry;
with closed soffits it reports an unresolved ridge enclosure. Structural ridge
systems retain that behavior by default and reject `wall` in this builder:
their end support and overhang detail need a separate design. Do not shave or
notch a structural beam to fit trim. See `docs/ridge-overhang-research.md` for
sources and rationale.


### Tail-depth fascia and extended bird-box returns

`gable_roof(..., eave_fascia_overlap=..., bird_box_return=..., fascia_assembly=...)`
can rip the eave fascia from its registered blank to the full plumb rafter-tail
depth plus an explicit vertical overlap. The fixture uses the plumb thickness of
the rake soffit as overlap: `(7.25 + .375) * sqrt(1.25)` gives an 8.525-inch fascia
face from a 1×10 blank. The bird-box infill then starts at the eave as a triangle.
`bird_box_return` is the inward distance from the gable framing corner to the
return's plumb end; the fixture uses `3 + 4` inches, measured from its gable trim's
inside edge. The base and back closure extend to that station and clear the trim.

The raised soffit uses 2×4 purchase blanks scribed only where they pass beneath
actual rafters. Their sloping cuts must contact those rafters; actual remaining
tail-face contact and panel bearing are checked. These cleats are not full-depth
spanning joists. Their attachment and thin-tail fastening remain explicitly
unverified. Unscribed portions retain the original full depth. The legacy deeper
fascia/rectangular-support detail remains available by omitting the overlap.

`fascia_assembly` assigns the two eave and four rake fascia boards to a separate
viewer assembly. Their geometric requirements remain part of the roof builder.
The fixture names this toggle **04 / Fascia**; bird-box closures and soffits stay
with the roof/soffit assembly.


Sheet siding uses a centered horizontal grid over each wall’s finish span: full interior sheets and equal-width edge panels. The minimum sheet count keeps those edge panels at least half a sheet wide. Gable siding uses the same grid and may span the peak in one cut panel. Door/window cutouts stay within each connected physical sheet, including panels with holes or notches; disconnected remnants are separate parts. Sheathing and lining retain their framing-based grids.


### Configurable siding layout

`wall_enclosure(..., siding_layout='centered', siding_offset=0)` keeps equal end
panels and full interior sheets. Use `siding_layout='start'` to place full sheets
from the finished wall edge. With that layout, a positive `siding_offset` is the
distance from that edge to the first joint; it must be less than a sheet width.
Zero starts with a full sheet. Gable siding shares the selected grid. A nonzero
offset with `centered` is rejected. These are layout preferences; both modes retain
stock, coverage, opening and backing checks.

The [framed shed example](../examples/framed-shed/README.md) composes these APIs
and records one set of architectural choices. Boxed versus triangular return
faces follow the chosen fascia/soffit depth and return length; the worked example
is not a universal corner detail. For a different construction system, compose
project-owned assemblies with the same relevant geometric requirements.
