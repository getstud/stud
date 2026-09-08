"""Transactional assembly generation shared by construction builders."""
from dataclasses import dataclass, field

from .assemblies import WallFrame, _number
from .model import Project


@dataclass
class Assembly:
    id: str
    frame: WallFrame
    roles: dict = field(default_factory=dict)
    interfaces: dict = field(default_factory=dict)

    @property
    def part_ids(self):
        return list(dict.fromkeys(self.roles.values()))


class Builder:
    def __init__(self, project, id, frame, name, assembly):
        if not isinstance(id, str) or not id.strip():
            raise ValueError('Assembly needs a stable nonempty ID')
        if not isinstance(frame, WallFrame):
            raise ValueError('frame must be a WallFrame')
        spec = project.validation
        if spec and spec.get('version') != 1:
            raise ValueError('Unsupported validation contract version')
        for key in ('rules', 'requirements', 'unverified'):
            if not isinstance(spec.get(key, []), list):
                raise ValueError(f'{key} must be a list')
        self.target = project
        self.project = Project(project.name)
        self.project.stocks = project.stocks.copy()
        self.project.validation = {'version': 1, 'rules': [], 'requirements': [], 'unverified': []}
        self.result = Assembly(id, frame)
        self.assembly = assembly
        self.source = {'builder': name, 'version': 1, 'component': id}

    def box(self, role, stock, origin, size, **kw):
        pid = f'{self.result.id}.{role}'
        center=self.result.frame.point(*(o+d/2 for o,d in zip(origin,size)))
        self.project.box(pid, self.assembly, stock, size=size,
                         origin=[c-d/2 for c,d in zip(center,size)],
                         rotation=(0,0,self.result.frame.angle), **kw)
        return self.register(role, self.project.parts[-1])

    def register(self, role, part):
        part.update(component=self.result.id, role=role)
        self.result.roles[role] = part['id']
        return part['id']

    def require(self, suffix, label, kind, parts, **kw):
        rid = f'{self.result.id}.{suffix}'
        self.project.validation['rules'].append(dict(id=rid, kind=kind, parts=list(parts),
                                                     source=self.source, **kw))
        self.project.validation['requirements'].append(dict(id=rid, rule_id=rid,
            component=self.result.id, label=label, parts=list(parts)))
        return rid

    def unverified(self, suffix, message):
        self.project.validation['unverified'].append(dict(rule=f'{self.result.id}.{suffix}', message=message))

    def commit(self):
        # Presence is a requirement independent of stock/collision scopes.
        self.require('members', 'All generated construction members remain present',
                     'assembly_presence', [p['id'] for p in self.project.parts])
        existing = {p['id'] for p in self.target.parts}
        generated = [p['id'] for p in self.project.parts]
        if len(set(generated)) != len(generated) or existing.intersection(generated):
            raise ValueError(f'{self.result.id}: generated part ID already exists')
        for key in ('rules', 'requirements'):
            ids = [r['id'] for r in self.project.validation[key]]
            old = {r.get('id') for r in self.target.validation.get(key, [])}
            if len(ids) != len(set(ids)) or old.intersection(ids):
                raise ValueError(f'{self.result.id}: generated {key} ID already exists')
        self.target.parts.extend(self.project.parts)
        if not self.target.validation:
            self.target.validation.update(version=1, automatic=['solid_collision', 'stock_fit'])
        for key in ('rules', 'requirements', 'unverified'):
            self.target.validation.setdefault(key, []).extend(self.project.validation[key])
        self.target.notes.extend(self.project.notes)
        return self.result


def section(project, stock):
    if stock not in project.stocks or not project.stocks[stock].section:
        raise ValueError(f'{stock}: a lumber section is required')
    return sorted(project.stocks[stock].section)


def positions(length, spacing, thickness):
    """Member lower faces; regular centerlines, closed perimeter at both ends."""
    _number(spacing, 'spacing', minimum=thickness)
    if length <= 2*thickness:
        raise ValueError('Assembly must fit two boundary members')
    points = [0]
    center = spacing
    while center+thickness/2 < length-thickness:
        points.append(center-thickness/2)
        center += spacing
    points.append(length-thickness)
    if any(b-a < thickness for a,b in zip(points, points[1:])):
        raise ValueError('Member layout overlaps near boundary')
    return points
