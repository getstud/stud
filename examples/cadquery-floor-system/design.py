"""Generic composition fixture. Dimensions demonstrate layout, not capacity."""
import cadquery as cq
from stud.cad import Model
from stud.bulk import volume_demand
from stud.framing import MemberProfile, AnchorDetail, anchored_sill
from stud.floors import Bearing, Opening, HangerDetail, frame_floor, deck_floor

LENGTH, WIDTH = 192, 120
WALL_TOP, SILL_DEPTH = 0, 1.5
INCLUDE_DECK = False
OPENINGS = [Opening('stairs', 30, 33, 30, 30)]
JOIST = MemberProfile(2, 9.5, 'fixture.ijoist', (96, 144, 192, 240),
    flange=1.125, web=.375, unresolved=('Select engineered product and verify loads and span.',))
RIM = MemberProfile(1.125, JOIST.depth, 'fixture.rim', (96, 144, 192, 240),
    unresolved=('Select rim product and fastening.',))
OPENING_STOCK = MemberProfile(3.5, JOIST.depth, 'fixture.header', (96, 144, 192, 240),
    unresolved=('Size headers and trimmers for opening reactions.',))
SILL = MemberProfile(5.5, SILL_DEPTH, 'fixture.treated', (120, 144, 192),
    unresolved=('Specify treated sill product.',))
HANGER = HangerDetail('fixture.hanger', 2, 7, .0625,
    ('Select rated hanger and its fastening schedule.',))
ANCHOR = AnchorDetail('fixture.anchor', .5, .5625, 7, 1, 2, .125, .4375,
    ('Verify anchorage product, embedment, edge distances and loads.',))

model = Model('Composable floor study', units='in')
# These seats stand in for interfaces supplied by a foundation/beam design.
bearings = []
for name, x in [('west', SILL.width/2), ('middle', LENGTH/2), ('east', LENGTH-SILL.width/2)]:
    pid = 'support.'+name
    model.part(pid, cq.Workplane('XY').box(8, WIDTH, 12, centered=(True, False, False))
        .translate((x, 0, WALL_TOP-12)), material='fixture.concrete')
    model.requirement(pid+'.valid', 'solid_valid', [pid])
    bearings.append(Bearing('sill.'+name, x, SILL.width, WALL_TOP+SILL_DEPTH))
volume_demand(model, 'supports.purchase', product_id='fixture.concrete', specification={},
    object_ids=['support.'+name for name in ('west','middle','east')], purchase_unit='yd3',
    unresolved=['Provide the supporting foundation/beam design and site basis.'])

# Named sill interfaces let framing and anchor exclusions derive from each other.
# All targets are resolved when Python finishes executing.
floor = frame_floor(model, object_id='floor', length=LENGTH, width=WIDTH,
    joist=JOIST, rim=RIM, bearings=bearings, spacing=16, min_bearing=1.5,
    openings=OPENINGS, opening_stock=OPENING_STOCK, hanger=HANGER,
    unresolved=['Establish project loads and verify the complete load path.'])
deck = None
if INCLUDE_DECK:
    deck = deck_floor(model, floor, product_id='fixture.panel', thickness=.75,
        sheet_size=(48, 96), gap=.125,
        seam_exclusions=[(b.x-ANCHOR.washer_width/2,b.x+ANCHOR.washer_width/2) for b in bearings],
        unresolved=['Select panel rating and fastening.'])
for bearing in bearings:
    name = bearing.part_id.split('.')[-1]
    anchored_sill(model, object_id=bearing.part_id,
        start=(bearing.x, 0, bearing.top), end=(bearing.x, WIDTH, bearing.top),
        stock=SILL, anchor=ANCHOR, support='support.'+name,
        max_spacing=48, end_distance=12, min_end=3,
        avoid=floor['parts']+floor['hangers']+(deck['backing']+deck['panels'] if deck else []))
