"""Connected wall set-out, resolved before registering any physical members.

Python specifications are the source of truth. Re-execution resolves references,
openings and junctions afresh; there is no incremental dependency graph. Only
planar masks use OCCT here. No finished members or Model records are created.
"""
from dataclasses import dataclass, replace
import math

import cadquery as cq
from .solids import prism
from .framing_geometry import polygon_intervals

_EPS = 1e-6


def _positive(*values):
    return all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in values)


def _point(p):
    return len(p) == 2 and all(math.isfinite(v) for v in p)


@dataclass(frozen=True)
class WallLine:
    """Named directed building edge; left of start→end is the inside face."""
    id: str
    start: tuple
    end: tuple
    base: float

    def __post_init__(self):
        object.__setattr__(self, 'start', tuple(self.start))
        object.__setattr__(self, 'end', tuple(self.end))
        if not self.id or not _point(self.start) or not _point(self.end) or math.dist(self.start, self.end) < _EPS or not math.isfinite(self.base):
            raise ValueError('A named wall line needs distinct finite endpoints and a base datum.')

    def offset(self, distance, *, id=None):
        length = math.dist(self.start, self.end)
        nx, ny = -(self.end[1]-self.start[1])/length, (self.end[0]-self.start[0])/length
        return WallLine(id or self.id, tuple(p+d*distance for p, d in zip(self.start, (nx, ny))),
                        tuple(p+d*distance for p, d in zip(self.end, (nx, ny))), self.base)


@dataclass(frozen=True)
class WallOpening:
    """Rough-opening envelope, measured from a run's directed start.

    station is its left edge. Movement is fixed unless max_shift is supplied.
    Unit dimensions and clear passage are separate optional evidence; neither
    changes the rough opening implicitly. Details are composed by stud.walls.
    """
    id: str
    station: float
    width: float
    height: float
    sill: float = 0
    margin: float = 3
    max_shift: float = 0
    detail: object = None
    unit_size: tuple | None = None
    clear_size: tuple | None = None
    shared_jambs: bool = False

    def __post_init__(self):
        if not self.id or not _positive(self.width, self.height) or not all(math.isfinite(v) for v in (self.station, self.sill, self.margin, self.max_shift)) or min(self.sill, self.margin, self.max_shift) < 0:
            raise ValueError('Invalid rough opening dimensions or movement allowance.')
        for key in ('unit_size', 'clear_size'):
            if getattr(self, key) is not None:object.__setattr__(self, key, tuple(getattr(self, key)))
        for size in (self.unit_size, self.clear_size):
            if size is not None and (len(size) != 2 or not _positive(*size)):
                raise ValueError('Unit and passage dimensions must be positive pairs.')


@dataclass(frozen=True)
class WallRun:
    id: str
    line: WallLine
    height: float
    depth: float
    thickness: float = 1.5
    spacing: float = 16
    alignment: str = 'outside'
    footprint: tuple = ()
    openings: tuple = ()
    priority: int = 0

    def __post_init__(self):
        object.__setattr__(self, 'openings', tuple(self.openings))
        object.__setattr__(self, 'footprint', tuple(tuple(p) for p in self.footprint))
        if not self.id or not isinstance(self.line, WallLine) or not _positive(self.height, self.depth, self.thickness, self.spacing) or self.height <= 3*self.thickness or self.spacing <= self.thickness:
            raise ValueError('Invalid wall stock, height or spacing.')
        if self.alignment not in ('outside', 'center', 'inside'):
            raise ValueError('Wall alignment must be outside, center or inside.')
        if self.footprint and (len(self.footprint) < 3 or not all(_point(p) for p in self.footprint)):
            raise ValueError('A wall footprint needs finite XY vertices.')
        if len({o.id for o in self.openings}) != len(self.openings):
            raise ValueError('Opening IDs must be unique within each wall.')

    @property
    def outside(self):
        return self.line.offset(-{'outside': 0, 'center': self.depth/2, 'inside': self.depth}[self.alignment])

    def face(self, face, *, id=None):
        """Reference another wall's face without duplicating coordinates."""
        if face not in ('outside', 'center', 'inside'):
            raise ValueError('Unknown wall face.')
        return self.outside.offset({'outside': 0, 'center': self.depth/2, 'inside': self.depth}[face], id=id)


@dataclass(frozen=True)
class JunctionDetail:
    """Opposite top-course ownership gives laps at compatible junctions.

    Explicit run priority selects the through wall; IDs break ties. Reordering
    declarations never changes the result. Unequal elevations do not lap.
    """
    lap_reach: float = 24
    corner_backing: str = 'unresolved'

    def __post_init__(self):
        if not _positive(self.lap_reach) or self.corner_backing not in ('unresolved', 'clips'):
            raise ValueError('Select a positive lap reach and supported corner-backing policy.')


@dataclass(frozen=True)
class ResolvedWall:
    run: WallRun
    lower: tuple
    upper: tuple
    openings: tuple
    neighbors: tuple


@dataclass(frozen=True)
class WallLayout:
    walls: tuple
    adjustments: tuple
    junction: JunctionDetail


def _box(x, y, dx, dy):
    return cq.Workplane('XY').box(dx, dy, 1, centered=(False, False, False)).val().translate((x, y, 0))


def _location(line):
    a, b = line.start, line.end
    return cq.Plane(origin=(*a, 0), xDir=(b[0]-a[0], b[1]-a[1], 0), normal=(0, 0, 1)).location


def _polygons(shape):
    result = []
    for face in shape.Faces():
        if face.normalAt().z < .99 or face.Area() < 1e-6:
            continue
        if face.innerWires():
            raise ValueError('A wall junction formed an enclosed hole; split the wall run.')
        points = tuple((round(v.X, 9), round(v.Y, 9)) for v in face.outerWire().Vertices())
        # OCCT vertex enumeration is stable within a wire, but choose a canonical
        # start and direction so equal input sets produce equal value records.
        i = min(range(len(points)), key=points.__getitem__)
        a = points[i:]+points[:i]
        reverse = tuple(reversed(points));i = min(range(len(reverse)), key=reverse.__getitem__)
        result.append(min(a, reverse[i:]+reverse[:i]))
    return tuple(sorted(result))


def _near(a, b):
    aa, bb = a.BoundingBox(), b.BoundingBox()
    return all(getattr(aa, k+'min') <= getattr(bb, k+'max')+_EPS and getattr(aa, k+'max') >= getattr(bb, k+'min')-_EPS for k in 'xy')


def layout_walls(walls, *, junction=JunctionDetail()):
    """Resolve a connected set independently of declaration order.

    Nonrectangular footprints may describe angled/mitered ends, but must stay in
    their run's stock strip. Coincident runs are rejected: a shared physical wall
    is authored once and can be referenced by either room.
    """
    walls = tuple(sorted(walls, key=lambda w: (w.priority, -math.dist(w.line.start, w.line.end), w.id)))
    if not walls or len({w.id for w in walls}) != len(walls):
        raise ValueError('Supply uniquely named wall runs.')
    masks, strips, locations, neighbors = {}, {}, {}, {}
    for w in walls:
        length = math.dist(w.line.start, w.line.end);loc = _location(w.outside)
        strip = _box(0, 0, length, w.depth).moved(loc)
        mask = prism(w.footprint, 1) if w.footprint else strip
        if not mask.isValid() or not mask.Solids() or mask.Volume() <= _EPS:
            raise ValueError(f'{w.id}: invalid wall footprint.')
        # Angled ends can extend beyond the baseline; cross-section must fit.
        wide = _box(-junction.lap_reach, 0, length+2*junction.lap_reach, w.depth).moved(loc)
        if mask.cut(wide).Volume() > _EPS:
            raise ValueError(f'{w.id}: footprint extends beyond the selected wall stock strip.')
        masks[w.id], strips[w.id], locations[w.id] = mask, wide, loc
        neighbors[w.id] = []
    for i, w in enumerate(walls):
        for other in walls[i+1:]:
            a, b = masks[w.id], masks[other.id]
            if not _near(a, b) or a.distance(b) > _EPS:
                continue
            if min(w.line.base+w.height, other.line.base+other.height) <= max(w.line.base, other.line.base)+_EPS:
                continue
            common = a.intersect(b).Volume()
            if common >= min(a.Volume(), b.Volume())-_EPS:
                raise ValueError(f'{w.id}/{other.id}: duplicate or wholly shared run; author the wall once.')
            if abs(w.line.base-other.line.base) > _EPS and common > _EPS:
                raise ValueError(f'{w.id}/{other.id}: overlapping walls at different bases need a split junction.')
            neighbors[w.id].append(other.id);neighbors[other.id].append(w.id)
    lower, upper = {}, {}
    for reverse, target in ((False, lower), (True, upper)):
        used = []
        for w in reversed(walls) if reverse else walls:
            shape = lower[w.id] if reverse else masks[w.id]
            length = math.dist(w.line.start, w.line.end)
            strip = strips[w.id] if reverse else _box(0, 0, length, w.depth).moved(locations[w.id])
            for other in walls:
                if other.id not in neighbors[w.id] or abs(w.line.base-other.line.base) > _EPS:
                    continue
                if reverse and abs(w.height-other.height) > _EPS:
                    continue
                neighbor = lower[other.id] if reverse else masks[other.id]
                shape = shape.fuse(neighbor.intersect(strip))
            for previous, previous_wall in used:
                # Ownership only applies to vertically overlapping courses.
                same = abs(w.line.base-previous_wall.line.base) < _EPS
                if reverse:same = same and abs(w.height-previous_wall.height) < _EPS
                if same and _near(shape, previous):shape = shape.cut(previous)
            shape = shape.clean()
            if not shape.Solids() or shape.Volume() < _EPS:
                raise ValueError(f'{w.id}: junction ownership removed the entire run.')
            target[w.id] = shape;used.append((shape, w))
    resolved, adjustments = [], []
    for w in walls:
        lo = _polygons(lower[w.id].moved(locations[w.id].inverse))
        hi = _polygons(upper[w.id].moved(locations[w.id].inverse))
        ranges = sorted(interval for poly in lo for interval in polygon_intervals(poly, w.depth/2))
        openings = []
        for o in sorted(w.openings, key=lambda o: (o.station, o.id)):
            fit_ranges = [(0, math.dist(w.line.start, w.line.end))] if o.shared_jambs else ranges
            choices = [(a+o.margin, b-o.width-o.margin) for a, b in fit_ranges if b-a >= o.width+2*o.margin-_EPS]
            if openings:
                previous = openings[-1]
                choices = [(max(a, previous.station+previous.width+previous.margin+o.margin), b) for a, b in choices]
            choices = [(max(a, o.station-o.max_shift), min(b, o.station+o.max_shift)) for a, b in choices]
            choices = [(a, b) for a, b in choices if a <= b+_EPS]
            if not choices:
                raise ValueError(f'{w.id}/{o.id}: fixed opening/jambs conflict with a junction or another opening; revise the station or explicitly permit bounded movement.')
            station = min((min(max(o.station, a), b) for a, b in choices), key=lambda x: (abs(x-o.station), x))
            if abs(station-o.station) > _EPS:adjustments.append((w.id, o.id, station-o.station))
            openings.append(replace(o, station=station))
        resolved.append(ResolvedWall(w, lo, hi, tuple(openings), tuple(sorted(neighbors[w.id]))))
    return WallLayout(tuple(resolved), tuple(adjustments), junction)
