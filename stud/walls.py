"""Stock wall framing from connected set-out and reusable opening details.

Plan once, inspect the immutable members, then register. Changing one opening or
wall input regenerates its dependents while station-based field IDs stay stable.
Dimensions are native project units; callers select actual stock and details.
"""
from dataclasses import dataclass, replace
import math
import cadquery as cq

from .wall_layout import WallLayout, JunctionDetail, layout_walls, _polygons, _positive
from .framing_geometry import polygon_intervals
from .solids import prism
from .stock import StockParts


@dataclass(frozen=True)
class HeaderDetail:
    depth: float
    ply_width: float = 1.5
    plies: int = 2
    jacks: int = 1
    cap: float = 1.5
    unresolved: tuple = ('Select header species/grade, sizing, reactions and fastening.',)

    def __post_init__(self):
        object.__setattr__(self, 'unresolved', tuple(self.unresolved))
        if not _positive(self.depth, self.ply_width) or not isinstance(self.plies, int) or self.plies < 1 or not isinstance(self.jacks, int) or self.jacks < 1 or not math.isfinite(self.cap) or self.cap < 0:
            raise ValueError('Invalid built-up header detail.')


@dataclass(frozen=True)
class PocketDetail:
    """Selected pocket envelope and face-stock; opening includes pocket + passage."""
    length: float
    face_width: float
    face_depth: float
    product_id: str
    unresolved: tuple = ('Confirm the selected kit, track and required rough opening.',)

    def __post_init__(self):
        object.__setattr__(self, 'unresolved', tuple(self.unresolved))
        if not _positive(self.length, self.face_width, self.face_depth) or not self.product_id:
            raise ValueError('A pocket needs a named product and positive stock/envelope sizes.')


@dataclass(frozen=True)
class TransomDetail:
    """A separate rail within a stacked opening, supported by its own jacks."""
    elevation: float
    header: HeaderDetail
    sill_thickness: float

    def __post_init__(self):
        if not _positive(self.elevation, self.sill_thickness) or not isinstance(self.header, HeaderDetail):
            raise ValueError('Invalid stacked-opening support detail.')


@dataclass(frozen=True)
class OpeningDetail:
    header: HeaderDetail
    pocket: PocketDetail | None = None
    transom: TransomDetail | None = None
    unresolved: tuple = ('Confirm selected unit rough-opening allowance and sill elevation.',)

    def __post_init__(self):
        object.__setattr__(self, 'unresolved', tuple(self.unresolved))
        if not isinstance(self.header, HeaderDetail) or (self.pocket is not None and not isinstance(self.pocket, PocketDetail)) or (self.transom is not None and not isinstance(self.transom, TransomDetail)):
            raise ValueError('Opening details need typed header, pocket and transom selections.')


@dataclass(frozen=True)
class PlateDetail:
    max_length: float = 144
    splice_offset: float = 72
    min_offset: float = 24

    def __post_init__(self):
        if not _positive(self.max_length, self.splice_offset, self.min_offset) or not self.min_offset <= self.splice_offset <= self.max_length-self.min_offset:
            raise ValueError('Top-plate splices must have the selected minimum offset in both directions.')


@dataclass(frozen=True)
class FramingDetail:
    plates: PlateDetail = PlateDetail()
    stock_lengths: tuple = (96, 120, 144, 192)
    kerf: float = .125
    min_section_fraction: float = .5
    unresolved: tuple = ('Select lumber species/grade, adopted fastening schedule, wall-to-floor ties and bracing.',)

    def __post_init__(self):
        object.__setattr__(self, 'stock_lengths', tuple(self.stock_lengths))
        object.__setattr__(self, 'unresolved', tuple(self.unresolved))
        if not self.stock_lengths or not _positive(*self.stock_lengths) or not math.isfinite(self.kerf) or self.kerf < 0 or not 0 < self.min_section_fraction <= 1 or self.plates.max_length > max(self.stock_lengths):
            raise ValueError('Invalid framing stock or retained-section policy.')


@dataclass(frozen=True)
class WallMember:
    id: str
    wall_id: str
    role: str
    origin: tuple
    size: tuple
    profile: tuple
    section: tuple
    length: float
    product_id: str | None = None
    bearing_strips: tuple = ()
    bearing_zones: tuple = ()


@dataclass(frozen=True)
class WallPlan:
    layout: WallLayout
    detail: FramingDetail
    members: tuple
    expected: tuple
    issues: tuple


def _area(poly):
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(poly, poly[1:]+poly[:1])))/2


def _key(x):
    return f'{x:.9f}'.rstrip('0').rstrip('.') if x else '0'


def _intervals(lo, hi, voids):
    for a, b in sorted(voids):
        if a > lo+1e-6:yield lo, min(a, hi)
        lo = max(lo, b)
        if lo >= hi-1e-6:return
    if hi > lo+1e-6:yield lo, hi


def plan_wall_members(layout, *, detail=FramingDetail()):
    """Resolve physical inventory and section conflicts before mutating a Model.

    Planar cuts precede member extrusion. Missing required jambs remain expected
    inventory and geometry issues; clipping cannot silently erase their intent.
    """
    if not isinstance(layout, WallLayout):
        raise ValueError('Supply the connected layout returned by layout_walls.')
    members, expected, issues = [], [], []
    for resolved in layout.walls:
        w = resolved.run;t = w.thickness;d = w.depth;h = w.height
        masks = [cq.Compound.makeCompound([prism(poly, 1) for poly in polygons]) for polygons in (resolved.lower, resolved.upper)]
        lo = min(x for poly in resolved.lower for x, y in poly);hi = max(x for poly in resolved.lower for x, y in poly)
        def board(key, role, x, y, z, dx, dy, dz, *, mask=0, section=None, required=False, product_id=None, bearing_strips=()):
            pid = w.id+'.'+key
            if min(dx, dy, dz) <= 1e-6:
                if required:expected.append(pid);issues.append((pid, 'Required member has no positive extent.'))
                return
            rect = cq.Workplane('XY').box(dx, dy, 1, centered=(False, False, False)).translate((x, y, 0)).val()
            polygons = _polygons(rect.intersect(masks[mask]).clean())
            if not polygons:
                if required:expected.append(pid);issues.append((pid, 'Junction removes required framing. Revise the opening or junction detail.'))
                return
            if required and len(polygons) != 1:
                expected.append(pid);issues.append((pid, 'Required member is disconnected by its junction cut.'))
            for poly in polygons:
                # A physical piece receives a stable coordinate key when split.
                px = min(a for a, b in poly)
                split = len(polygons) > 1
                keyid = pid+('.piece.at_'+_key(px)+'_'+_key(min(b for a, b in poly)) if split else '')
                vertical = role in ('stud', 'king', 'jack', 'cripple', 'pocket_stud')
                ox = x if vertical or not split else px
                sx = dx if vertical or not split else max(a for a, b in poly)-px
                profile = tuple((a-ox, b-y) for a, b in poly)
                length = dz if vertical else sx
                if length > max(detail.stock_lengths)+1e-6:
                    raise ValueError(f'{keyid}: member exceeds available stock; select longer stock or a splice detail.')
                expected.append(keyid)
                fraction = _area(profile)/(dx*dy)
                if vertical and fraction < (1-1e-6 if role in ('king', 'jack') else detail.min_section_fraction):
                    issues.append((keyid, f'Junction retains {fraction:.1%} of the authored section; select a valid corner/shared-post detail.'))
                members.append(WallMember(keyid, w.id, role, (ox, y, z), (sx, dy, dz), profile, section or (t, d), length, product_id, bearing_strips))
        def plates(level, polygons, mask, z, offset):
            low = min(x for poly in polygons for x, y in poly);high = max(x for poly in polygons for x, y in poly)
            length = detail.plates.max_length
            cadence = math.floor(length/w.spacing)*w.spacing
            if cadence <= 0:raise ValueError('Plate stock must accommodate at least one stud spacing.')
            phase = detail.plates.splice_offset % cadence
            if not detail.plates.min_offset <= phase <= cadence-detail.plates.min_offset:
                raise ValueError('Plate splice offset does not fit the stock limit and stud grid.')
            first_lower = math.floor((lo+length)/w.spacing)*w.spacing
            first = first_lower if level != 'top2' else first_lower+phase-cadence
            while first <= low+t:first += cadence
            cuts = [low]
            if high-low > length+1e-6:
                while first < high-1e-6:
                    if first-cuts[-1] > length+1e-6:
                        raise ValueError('Selected plate phase exceeds available stock at a junction.')
                    cuts.append(first)
                    if high-first <= length+1e-6:break
                    first += cadence
            cuts.append(high)
            voids = [(o.station, o.station+o.width) for o in resolved.openings if o.sill == 0] if level == 'bottom' else []
            for a, b in zip(cuts, cuts[1:]):
                for c, e in _intervals(a, b, voids):
                    board(f'plate.{level}.at_{_key(c)}', 'plate_'+level, c, 0, z, e-c, d, t, mask=mask)
        plates('bottom', resolved.lower, 0, 0, 0)
        plates('top1', resolved.lower, 0, h-2*t, 0)
        plates('top2', resolved.upper, 1, h-t, detail.plates.splice_offset)
        exclusions = []
        for o in resolved.openings:
            if not isinstance(o.detail, OpeningDetail) or not isinstance(o.detail.header, HeaderDetail):
                raise ValueError(f'{w.id}/{o.id}: select an explicit opening/header detail.')
            hd = o.detail.header
            if hd.plies*hd.ply_width > d+1e-6 or o.sill+o.height+hd.depth+hd.cap > h-2*t+1e-6:
                raise ValueError(f'{w.id}/{o.id}: header plies/cap do not fit the wall.')
            if o.shared_jambs or o.margin < (hd.jacks+1)*t:
                issues.append((w.id+'.opening.'+o.id, 'Jamb allowance requires a shared corner-post detail; ordinary full kings/jacks are not assured.'))
            margin = (hd.jacks+1)*t
            exclusions.append((o.station-margin, o.station+o.width+margin))
        # Every disconnected run and angled end needs a real full-section end
        # stud. Extreme polygon tips are not valid stud stations.
        ranges = [(lo, hi)]
        ys = sorted({0., d, *(min(d, max(0., y)) for poly in resolved.lower for x, y in poly)})
        samples = [y for a, b in zip(ys, ys[1:]) if b-a > 1e-8 for y in (a+1e-8, b-1e-8)]
        for y in samples:
            row = sorted(pair for poly in resolved.lower for pair in polygon_intervals(poly, y))
            merged = []
            for a, b in row:
                if merged and a <= merged[-1][1]+1e-7:merged[-1] = (merged[-1][0], max(merged[-1][1], b))
                else:merged.append((a, b))
            ranges = [(max(a, c), min(b, e)) for a, b in ranges for c, e in merged if min(b, e)-max(a, c) >= t-1e-7]
        ranges = [(a, b-t) for a, b in ranges if b-a >= t-1e-7]
        positions = []
        for a, b in ranges:
            group = sorted(set([a, b]+[k*w.spacing-t/2 for k in range(math.floor(a/w.spacing), math.ceil((b+t)/w.spacing)) if a+t < k*w.spacing-t/2 < b-t]))
            group = [x for i, x in enumerate(group) if i == 0 or x-group[i-1] >= t-1e-6]
            for x, y in list(zip(group, group[1:])):
                if y-x > w.spacing+1e-6:group.append((x+y)/2)
            positions.extend(group)
        if not positions:
            issues.append((w.id+'.field', 'No full-section field stud fits this wall footprint; revise the junction detail.'))
        for x in sorted(set(positions)):
            if not any(x+t > a+1e-6 and x < b-1e-6 for a, b in exclusions):
                board('stud.at_'+_key(x), 'stud', x, 0, t, t, d, h-3*t)
        for o in resolved.openings:
            x, width, sill = o.station, o.width, o.sill;head = sill+o.height;hd = o.detail.header;k = o.id
            for side in ('left', 'right'):
                kx = x-(hd.jacks+1)*t if side == 'left' else x+width+hd.jacks*t
                board(f'king.{k}.{side}', 'king', kx, 0, t, t, d, h-3*t, required=True)
                for j in range(hd.jacks):
                    jx = x-(j+1)*t if side == 'left' else x+width+j*t
                    board(f'jack.{k}.{side}'+(f'.{j}' if hd.jacks > 1 else ''), 'jack', jx, 0, t, t, d, head-t, required=True)
            ys = [d/2-hd.ply_width/2] if hd.plies == 1 else [i*(d-hd.ply_width)/(hd.plies-1) for i in range(hd.plies)]
            for i, y in enumerate(ys):
                board(f'header.{k}.ply{i}', 'header', x-hd.jacks*t, y, head, width+2*hd.jacks*t, hd.ply_width, hd.depth, section=(hd.ply_width, hd.depth), required=True)
            if hd.cap:board(f'header.{k}.cap', 'header_cap', x-hd.jacks*t, 0, head+hd.depth, width+2*hd.jacks*t, d, hd.cap, section=(hd.cap, d), required=True, bearing_strips=tuple((y, hd.ply_width) for y in ys))
            if sill:board(f'sill.{k}', 'sill', x, 0, sill-t, width, d, t, required=True)
            positions = [x]+[i*w.spacing-t/2 for i in range(math.floor(x/w.spacing), math.ceil((x+width)/w.spacing)) if x+t < i*w.spacing-t/2 < x+width-2*t]+[x+width-t]
            for at in sorted(set(positions)):
                if sill:board(f'cripple.{k}.below.at_{_key(at)}', 'cripple', at, 0, t, t, d, sill-2*t)
                board(f'cripple.{k}.above.at_{_key(at)}', 'cripple', at, 0, head+hd.depth+hd.cap, t, d, h-2*t-head-hd.depth-hd.cap, bearing_strips=tuple((y, hd.ply_width) for y in ys) if not hd.cap else ())
            if o.detail.transom:
                rail = o.detail.transom;rh = rail.header
                if o.sill or rail.elevation+rh.depth+rail.sill_thickness >= head or rh.jacks != 1 or rh.cap or rh.ply_width*rh.plies > d or width <= 2*t:
                    raise ValueError(f'{w.id}/{k}: stacked rail must fit within a floor-level opening with one jack each side and a separate sill.')
                rys = [d/2-rh.ply_width/2] if rh.plies == 1 else [i*(d-rh.ply_width)/(rh.plies-1) for i in range(rh.plies)]
                for i, y in enumerate(rys):board(f'rail.{k}.ply{i}', 'header', x, y, rail.elevation, width, rh.ply_width, rh.depth, section=(rh.ply_width, rh.depth), required=True)
                board(f'rail.{k}.fixed_sill', 'header_cap', x, 0, rail.elevation+rh.depth, width, d, rail.sill_thickness, section=(rail.sill_thickness, d), required=True, bearing_strips=tuple((y, rh.ply_width) for y in rys))
                for side, jx in (('left', x), ('right', x+width-t)):
                    board(f'plate.rail.{k}.{side}', 'plate_bottom', jx, 0, 0, t, d, t, required=True)
                    board(f'jack.rail.{k}.{side}', 'jack', jx, 0, t, t, d, rail.elevation-t, required=True)
            if o.detail.pocket:
                pocket = o.detail.pocket
                if sill or pocket.length >= width or pocket.length < 2*pocket.face_width or 2*pocket.face_depth > d or o.detail.transom:
                    raise ValueError(f'{w.id}/{k}: pocket stock/envelope does not fit the opening.')
                for face, y in enumerate((0, d-pocket.face_depth)):
                    board(f'pocket.{k}.base{face}', 'plate_bottom', x, y, 0, pocket.length, pocket.face_depth, t, section=(t, pocket.face_depth), product_id=pocket.product_id+'.base')
                    for at in (x, x+pocket.length-pocket.face_width):
                        board(f'stud.pocket.{k}.{face}.at_{_key(at)}', 'pocket_stud', at, y, t, pocket.face_width, pocket.face_depth, head-t, section=(pocket.face_width, pocket.face_depth), product_id=pocket.product_id+'.stud', required=True)
    # Top-course support is planned from the intended stud/header seats. At an
    # angled end the stock can project beyond its full-section end stud; checking
    # the polygon tip would incorrectly demand wood in that projection.
    supported = []
    for member in members:
        if member.role != 'plate_top1':supported.append(member);continue
        x, y, z = member.origin
        plate = prism(member.profile, 1)
        contacts = []
        for peer in members:
            if peer.wall_id != member.wall_id or abs(peer.origin[2]+peer.size[2]-z) > 1e-6:continue
            px, py, pz = peer.origin
            if px+peer.size[0] <= x or px >= x+member.size[0]:continue
            common = plate.intersect(prism(peer.profile, 1).translate((px-x, py-y, 0)))
            if common.Volume() > 1e-6:
                bb = common.BoundingBox()
                contacts.append((bb.xmin, bb.ymin, bb.xmax, bb.ymax, common.Volume()))
        zones = ()
        if contacts:
            first = min(contacts, key=lambda c: c[0]);last = max(contacts, key=lambda c: c[2])
            zones = tuple(dict.fromkeys((first, last)))
        else:issues.append((member.id, 'No planned stud/header seat supports this top-plate piece.'))
        supported.append(replace(member, bearing_zones=zones))
    members = supported
    products = {}
    for m in members:
        if m.product_id:
            key = (m.wall_id, m.product_id)
            if key in products and products[key] != m.section:
                raise ValueError('One stock product cannot describe different sections.')
            products[key] = m.section
    ids = [m.id for m in members]
    if len(ids) != len(set(ids)):
        raise ValueError('Member IDs collide; separate opening IDs and station positions.')
    return WallPlan(layout, detail, tuple(members), tuple(sorted(set(expected))), tuple(issues))


def frame_walls(model, walls=None, *, object_id='walls', plan=None, junction=JunctionDetail(),
                detail=FramingDetail(), floor_supports=(), obstacles=(), id_aliases=None):
    """Register a plan, its stock purchases, inventory, openings and bearing intent.

    id_aliases is an optional migration map from planned member IDs to existing
    full part IDs. It preserves project review references during a refactor.
    """
    if plan is None:plan = plan_wall_members(layout_walls(walls, junction=junction), detail=detail)
    elif walls is not None:raise ValueError('Supply wall inputs or an already resolved plan, not both.')
    aliases = id_aliases or {}
    if set(aliases)-set(plan.expected):raise ValueError('Migration aliases reference unknown planned members.')
    if any(not isinstance(value, str) or not value for value in aliases.values()):raise ValueError('Migration aliases need nonempty part IDs.')
    def pid(key):return aliases.get(key, object_id+'.'+key)
    if len({pid(key) for key in plan.expected}) != len(plan.expected):
        raise ValueError('Migration aliases must identify distinct physical members.')
    for target in (*floor_supports, *obstacles):
        if target not in model.shapes:raise ValueError('Unknown wall interface '+target)
    before = set(model.requirements)
    model.assembly(object_id, 'Wall framing')
    by_wall, member_map, planned = {}, {}, {m.id: m for m in plan.members}
    runs = {r.run.id: r for r in plan.layout.walls}
    for key, resolved in runs.items():
        w = resolved.run;line = w.outside;a, b = line.start, line.end
        loc = cq.Plane(origin=(*a, line.base), xDir=(b[0]-a[0], b[1]-a[1], 0), normal=(0, 0, 1)).location
        wid = object_id+'.'+key;model.assembly(wid, key, parent=object_id)
        stock = StockParts(model, parent=wid, demand_prefix=wid+'.purchase.')
        ids = []
        with model.batch():
            for m in (m for m in plan.members if m.wall_id == key):
                shape = prism(m.profile, m.size[2])
                blank = dict(size=list(m.size), cut_length=m.length, operations=[dict(kind='square_cut', finished_length=m.length), dict(kind='profile_cut', profile=m.profile, note='Junction profile in original XY stock axes, through Z.')])
                part = pid(m.id)
                stock.add(part, (shape, loc*cq.Location(cq.Vector(*m.origin)), blank), section=m.section, product_id=m.product_id, label=m.id[len(key)+1:])
                ids.append(part);member_map[m.id] = part
            stock.purchase(stock_lengths=plan.detail.stock_lengths, kerf=plan.detail.kerf)
            for group in stock._groups:
                model.demands[wid+'.purchase.'+group]['unresolved'].extend(plan.detail.unresolved)
            conn = model.connection(wid+'.assembly', parts=ids, description='Individual stock framing with split bottom plates and staggered double top courses.', unresolved=list(plan.detail.unresolved))
            model.step(wid+'.erect', 'Assemble, plumb and brace '+key, parts=ids, connections=[conn])
            for o in resolved.openings:
                detail_o = o.detail;hd = detail_o.header
                opening_parts = [pid(m.id) for m in plan.members if m.wall_id == key and '.'+o.id+'.' in m.id]
                model.connection(wid+'.opening.'+o.id, parts=opening_parts, description='Rough opening framed with separate header plies and explicit jamb stock.', unresolved=list(detail_o.unresolved+hd.unresolved+(detail_o.pocket.unresolved if detail_o.pocket else ()))+(['Verify tall-wall and stacked-light loads.'] if detail_o.transom else []))
                suffix = '.0' if hd.jacks > 1 else ''
                left, right = pid(key+'.jack.'+o.id+'.left'+suffix), pid(key+'.jack.'+o.id+'.right'+suffix)
                if left in model.shapes and right in model.shapes:
                    # Locations derive from the authored untrimmed stock axes.
                    p = model.reference(left, 'clear', point=(w.thickness, 0, o.sill-w.thickness))
                    q = model.reference(right, 'clear', point=(0, 0, o.sill-w.thickness))
                    top = model.reference(left, 'head', point=(w.thickness, 0, o.sill+o.height-w.thickness))
                    model.requirement(wid+'.opening.'+o.id+'.width', 'length', [p, q], threshold=o.width)
                    model.requirement(wid+'.opening.'+o.id+'.height', 'length', [p, top], threshold=o.height)
                else:
                    model.expect(wid+'.opening.'+o.id+'.jamb_inventory', parts=[left, right])
        by_wall[wid] = ids
    ids = list(member_map.values())
    for key, message in plan.issues:
        relevant = [pid(key)] if key in planned else [pid(m.id) for m in plan.members if m.wall_id == key.split('.opening.')[0]]
        model.connection(object_id+'.issue.'+key, parts=relevant, description=message, geometry_unresolved=True, unresolved=[message])
    for resolved in plan.layout.walls:
        if resolved.neighbors:
            w = resolved.run;wid = object_id+'.'+w.id
            model.connection(wid+'.junctions', parts=by_wall[wid], description='Resolved corner/T ownership and opposite same-height top-course laps.', unresolved=['Select and schedule drywall corner clips.' if plan.layout.junction.corner_backing == 'clips' else 'Select corner backing or a clip detail.']+['Specify lap fastening and check differing-height intersections.'])
    # Required contact areas come from planned cut sections/end zones, never from
    # the measured area of whatever support happened to survive generation.
    candidates = ids+list(floor_supports)
    bounds = {p: model.shapes[p]['world'].BoundingBox() for p in candidates}
    for m in plan.members:
        part = pid(m.id);a = bounds[part];seats = []
        for other in candidates:
            if other == part:continue
            b = bounds[other]
            if abs(a.zmin-b.zmax) < 1e-5 and a.xmin < b.xmax-1e-6 and a.xmax > b.xmin+1e-6 and a.ymin < b.ymax-1e-6 and a.ymax > b.ymin+1e-6:seats.append(other)
        if not seats:
            model.connection(part+'.unseated', parts=[part], description='No downward support at the planned bearing interface.', geometry_unresolved=True, unresolved=['Provide bearing or an explicitly designed attachment.'])
            continue
        full = m.role in ('stud', 'king', 'jack', 'cripple', 'pocket_stud', 'plate_bottom', 'plate_top2')
        if full and m.bearing_strips:
            for index, (y, width) in enumerate(m.bearing_strips):
                zone = prism(m.profile, 1).intersect(cq.Workplane('XY').box(m.size[0], width, 1, centered=(False, False, False)).translate((0, y, 0)).val())
                model.requirement(part+f'.bearing.ply{index}', 'support', [part]+seats, threshold=zone.Volume(), direction=[0, 0, -1], region_local=dict(min=[0, y, 0], max=[m.size[0], y+width, m.size[2]]))
        elif full:
            model.requirement(part+'.bearing', 'support', [part]+seats, threshold=_area(m.profile), direction=[0, 0, -1])
        elif m.role == 'plate_top1':
            for index, (x0, y0, x1, y1, area) in enumerate(m.bearing_zones):
                model.requirement(part+f'.bearing.seat{index}', 'support', [part]+seats, threshold=area, direction=[0, 0, -1], region_local=dict(min=[x0, y0, 0], max=[x1, y1, m.size[2]]))
            if m.bearing_zones and (m.bearing_zones[0][0] > 1e-5 or m.bearing_zones[-1][2] < m.size[0]-1e-5):
                model.connection(part+'.end_projection', parts=[part]+seats, description='Plate end projects beyond its planned full-section end seat.', unresolved=['Verify this end projection, junction fastening and load transfer.'])
        elif m.role in ('header', 'sill'):
            # Independently checked end seats prevent one good end hiding the other.
            t = runs[m.wall_id].run.thickness;dx, dy, dz = m.size
            for side, x in (('start', 0), ('end', max(0, dx-t))):
                zone = prism(m.profile, 1).intersect(cq.Workplane('XY').box(min(t, dx), dy, 1, centered=(False, False, False)).translate((x, 0, 0)).val())
                area = zone.Volume()
                if area > 1e-6:
                    model.requirement(part+'.bearing.'+side, 'support', [part]+seats, threshold=area, direction=[0, 0, -1], region_local=dict(min=[x, 0, 0], max=[min(dx, x+t), dy, dz]))
        else:
            # Caps span separated header plies. Their end strips require bearing
            # on both plies; a complete structural connection remains separate.
            dx, dy, dz = m.size
            for index, (y, width) in enumerate(m.bearing_strips):
                zone = prism(m.profile, 1).intersect(cq.Workplane('XY').box(dx, width, 1, centered=(False, False, False)).translate((0, y, 0)).val())
                model.requirement(part+f'.bearing.ply{index}', 'support', [part]+seats, threshold=zone.Volume(), direction=[0, 0, -1], region_local=dict(min=[0, y, 0], max=[dx, y+width, dz]))
    model.requirement(object_id+'.no_overlap', 'collision_free', ids, threshold=0)
    from .framing import _clear_of_existing
    _clear_of_existing(model, ids, obstacles, object_id+'.clear')
    for wall, opening, shift in plan.layout.adjustments:
        model.notes.append(f'{object_id}.{wall}/{opening}: explicitly permitted opening shift {shift:g}.')
    model.expect(object_id+'.inventory', parts=[pid(key) for key in plan.expected], requirements=sorted(set(model.requirements)-before), connections=[object_id+'.'+key+'.assembly' for key in runs])
    return dict(parts=ids, walls=by_wall, members=member_map, layout=plan.layout, plan=plan)
