"""Reusable assemblies that declare the geometric relationships they require."""
from dataclasses import dataclass, field
import math

from .model import Project


def _number(value, name, *, minimum=0, inclusive=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or (value < minimum if inclusive else value <= minimum)):
        raise ValueError(f'{name} must be finite and {">=" if inclusive else ">"} {minimum}')
    return value


@dataclass(frozen=True)
class WallFrame:
    """Wall-local U (along wall), V (inward), Z (up), from a floor datum.

    angle rotates U about world Z; inward=-1 mirrors the depth direction.
    Boxes rotate about their centers, matching Project.box and the viewer.
    """
    origin: tuple = (0, 0, 0)
    angle: float = 0
    inward: int = 1

    def __post_init__(self):
        if len(self.origin) != 3 or not all(math.isfinite(v) for v in self.origin):
            raise ValueError('Wall frame needs three finite origin coordinates')
        if not math.isfinite(self.angle) or self.inward not in (-1, 1):
            raise ValueError('Wall frame needs a finite angle and inward of -1 or 1')

    def point(self, u, v, z):
        c, s = math.cos(math.radians(self.angle)), math.sin(math.radians(self.angle))
        if abs(self.angle/90-round(self.angle/90)) < 1e-10:
            c, s = round(c), round(s)
        return (self.origin[0]+c*u-self.inward*s*v,
                self.origin[1]+s*u+self.inward*c*v, self.origin[2]+z)

    def box(self, origin, size):
        center = self.point(*(a+b/2 for a, b in zip(origin, size)))
        # Keep cardinal walls in the existing axis-aligned representation.
        if abs(self.angle/90-round(self.angle/90)) < 1e-10:
            if round(self.angle/90) % 2:
                size = (size[1], size[0], size[2])
            rotation = (0, 0, 0)
        else:
            rotation = (0, 0, self.angle)
        return dict(size=list(size), origin=[c-s/2 for c, s in zip(center, size)],
                    rotation=list(rotation))


@dataclass
class FramedOpening:
    id: str
    frame: WallFrame
    roles: dict
    dimensions: dict = field(default_factory=dict)

    def include_in_clearance(self, parts):
        """Tag host framing/finishes, including parts created after this builder.

        Door leaves and window units intentionally occupying the opening are
        excluded by the caller. Scope membership is resolved at validation time.
        """
        for part in parts:
            scopes = part.setdefault('validation_scopes', [])
            if self.id not in scopes:
                scopes.append(self.id)


def framed_opening(project, id, *, frame, start, width, bottom, height,
                   wall_height, stud_stock, header_stock, spacer_stock=None,
                   field_studs=(), assembly='Opening framing', tolerance=.001):
    """Create a two-ply rectangular opening and its geometric requirements.

    Host wall owns plates and removes displaced field studs. field_studs contains
    (stable original stud ID, local U) pairs wholly within the clear width; this
    builder replaces them with lower/upper cripples where space permits.
    Header sizing and fastening are design inputs, not structural approvals.
    """
    if not isinstance(id, str) or not id.strip():
        raise ValueError('Opening needs a stable nonempty ID')
    if not isinstance(frame, WallFrame):
        raise ValueError('frame must be a WallFrame')
    for value, name in ((width, 'width'), (height, 'height'),
                        (wall_height, 'wall_height'), (tolerance, 'tolerance')):
        _number(value, name)
    for value, name in ((start, 'start'), (bottom, 'bottom')):
        _number(value, name, inclusive=True)
    try:
        stud = project.stocks[stud_stock]
        header = project.stocks[header_stock]
    except KeyError as error:
        raise ValueError(f'Unknown opening stock: {error}') from error
    if not stud.section or not header.section:
        raise ValueError('Opening studs and headers require lumber sections')
    thickness, depth = sorted(stud.section)
    ply_width, header_depth = sorted(header.section)
    spacer = depth-2*ply_width
    top = bottom+height
    if start < 2*thickness or top+header_depth > wall_height-2*thickness:
        raise ValueError('Opening must leave room for kings and header below top plates')
    if top <= thickness or (bottom and bottom <= 2*thickness):
        raise ValueError('Opening must leave room for jacks and a raised sill')
    if spacer < -1e-8 or (spacer > 1e-8 and spacer_stock not in project.stocks):
        raise ValueError('Two header plies must fit wall depth; any gap needs spacer stock')
    spec = project.validation
    if spec and spec.get('version') != 1:
        raise ValueError('Unsupported validation contract version')
    for name in ('rules', 'requirements'):
        if not isinstance(spec.get(name, []), list):
            raise ValueError(f'{name} must be a list')

    # Stage geometry and checks so invalid inputs never leave a partial assembly.
    staged = Project(project.name)
    staged.stocks = project.stocks
    roles = {}
    source = {'builder': 'framed_opening', 'version': 1, 'component': id}

    def member(pid, role, stock, u, v, z, w, d, h, note=''):
        staged.box(pid, assembly, stock, **frame.box((u, v, z), (w, d, h)), note=note)
        staged.parts[-1]['component'] = id
        staged.parts[-1]['role'] = role
        roles[role] = pid

    end = start+width
    for edge, king, jack in [('left', start-2*thickness, start-thickness),
                             ('right', end+thickness, end)]:
        member(f'{id}.king.{edge}', f'king.{edge}', stud_stock, king, 0, thickness,
               thickness, depth, wall_height-3*thickness)
        member(f'{id}.jack.{edge}', f'jack.{edge}', stud_stock, jack, 0, thickness,
               thickness, depth, top-thickness)
    if bottom:
        member(f'{id}.sill', 'sill', stud_stock, start, 0, bottom-thickness,
               width, depth, thickness)
    for ply, inset in enumerate((0, depth-ply_width)):
        member(f'{id}.header.{ply}', f'header.{ply}', header_stock,
               start-thickness, inset, top, width+2*thickness, ply_width, header_depth,
               'Provisional two-ply header; capacity and fastening remain to be specified.')
    if spacer > 1e-8:
        member(f'{id}.header.spacer', 'header.spacer', spacer_stock,
               start-thickness, ply_width, top, width+2*thickness, spacer, header_depth)
    for pid, u in field_studs:
        _number(u, 'field stud position', inclusive=True)
        if u < start or u+thickness > end:
            raise ValueError('Cripple layout must fit wholly within the opening width')
        for label, z0, z1 in [('lower', thickness, bottom-thickness),
                              ('upper', top+header_depth, wall_height-2*thickness)]:
            if z1 > z0:
                member(f'{pid}.{label}', f'cripple.{pid}.{label}', stud_stock,
                       u, 0, z0, thickness, depth, z1-z0)

    opening = FramedOpening(id, frame, roles, dict(start=start, width=width, bottom=bottom, height=height, wall_depth=depth))
    opening.include_in_clearance(staged.parts)
    rules, requirements = [], []

    def require(suffix, label, kind, parts, **parameters):
        rule_id = f'{id}.{suffix}'
        rules.append(dict(id=rule_id, kind=kind, parts=parts, source=source,
                          tolerance=tolerance, **parameters))
        requirements.append(dict(id=rule_id, rule_id=rule_id, component=id,
                                 label=label, parts=parts))

    for ply in (0, 1):
        for edge in ('left', 'right'):
            require(f'bearing.{ply}.{edge}', f'Header ply {ply+1}: {edge} jack bearing',
                    'minimum_contact', [roles[f'header.{ply}'], roles[f'jack.{edge}']],
                    minimum_area=thickness*ply_width, normal=[0, 0, -1])
    require('clearance', 'Clear rough opening', 'opening_clearance',
            [p['id'] for p in staged.parts], scope=id,
            opening=frame.box((start, 0, bottom), (width, depth, height)))

    existing = {p['id'] for p in project.parts}
    if any(p['id'] in existing for p in staged.parts):
        raise ValueError(f'{id}: generated part ID already exists')
    existing_rules = {r.get('id') for r in spec.get('rules', [])}
    existing_requirements = {r.get('id') for r in spec.get('requirements', [])}
    if any(r['id'] in existing_rules or r['id'] in existing_requirements for r in rules):
        raise ValueError(f'{id}: generated check ID already exists')
    project.parts.extend(staged.parts)
    if not spec:
        spec.update(version=1, automatic=['solid_collision', 'stock_fit'])
    spec.setdefault('rules', []).extend(rules)
    spec.setdefault('requirements', []).extend(requirements)
    return opening
