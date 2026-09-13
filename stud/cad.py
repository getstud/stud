"""Completed CadQuery output and project meaning in declared project units.

Use ordinary CadQuery for geometry. Model publishes snapshots; it never wraps
booleans, sketches, selectors, or the rest of the CadQuery modeling language.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import inspect
import io
from pathlib import Path
import struct
import time

import cadquery as cq

from .contracts import StudError, atomic_write, digest, encoded
from .units import validate as validate_units, defaults as unit_defaults, requirement_units

_publication = ContextVar('stud_publication', default=None)


def location_matrix(location):
    transform = location.wrapped.Transformation()
    return [[transform.Value(r, c) for c in range(1, 5)] for r in range(1, 4)] + [[0, 0, 0, 1]]


def point_at(location, point):
    return list(cq.Vector(*point).transform(cq.Matrix(location.wrapped.Transformation())).toTuple())


def vector_at(location, vector):
    return [a-b for a,b in zip(point_at(location,vector),point_at(location,(0,0,0)))]


def shape_bounds(shape):
    box = shape.BoundingBox()
    return dict(min=[box.xmin, box.ymin, box.zmin], max=[box.xmax, box.ymax, box.zmax])


@contextmanager
def publication_context(callback, directory, runtime, settings, units='mm'):
    token = _publication.set(dict(callback=callback, directory=Path(directory), runtime=runtime, settings=settings,units=validate_units(units)))
    try:
        yield
    finally:
        _publication.reset(token)


class Model:
    def __init__(self, name, *, units=None):
        self.context = _publication.get()
        self._units=validate_units(units if units is not None else (self.context['units'] if self.context else 'mm'))
        if self.context and self.units!=self.context['units']:
            raise StudError('unit_mismatch','The model units must match the project; geometry is not converted implicitly.')
        self.name = name
        self.assemblies = {}
        self.objects = {}
        self.shapes = {}
        self.assets = {}
        self.references = {}
        self.requirements = {}
        self.expectations = {}
        self.demands = {}
        self.drawings = {}
        self.dimensions = {}
        self.steps = {}
        self.connections = {}
        self.notes = []
        self.timings = {'archive_seconds': 0.0, 'tessellation_seconds': 0.0}
        self._batch = None
        # The worker can retain a partially evaluated model after an exception.
        if self.context:
            self.context['callback']('model_created', self)

    @property
    def units(self):
        return self._units

    @units.setter
    def units(self, value):
        raise StudError('unit_mismatch','Model units are fixed at creation and cannot be reassigned.')

    def _unique(self, collection, key):
        if not isinstance(key, str) or not key.strip() or key in collection:
            raise StudError('duplicate_id', f'Expected a new persistent identity: {key}')

    def _provenance(self):
        root = Path.cwd().resolve()
        for frame in inspect.stack()[2:]:
            file = Path(frame.filename).resolve()
            if file.is_relative_to(root):
                return dict(file=file.relative_to(root).as_posix(), line=frame.lineno)
        return dict(file=None, line=None)

    def _parent_location(self, parent):
        if parent is None:
            return cq.Location()
        if parent not in self.assemblies:
            raise StudError('unresolved_reference', f'Unknown parent assembly: {parent}')
        assembly = self.assemblies[parent]
        return self._parent_location(assembly['parent']) * assembly['_location']

    def assembly(self, object_id, label=None, *, parent=None, location=None):
        self._unique({**self.assemblies, **self.objects}, object_id)
        location = location or cq.Location()
        world = self._parent_location(parent) * location
        self.assemblies[object_id] = dict(id=object_id, label=label or object_id, parent=parent,
            local_placement=location_matrix(location), placement=location_matrix(world),
            provenance=self._provenance(), _location=location)
        return object_id

    def part(self, object_id, shape, *, parent=None, label=None, location=None,
             material=None, blank=None, color='#d8b982', lineage=None, replace=False, mark=None):
        if replace:
            if object_id not in self.objects:
                raise StudError('unresolved_reference', f'Cannot replace an unknown part: {object_id}')
        else:
            self._unique({**self.assemblies, **self.objects}, object_id)
        if isinstance(shape, cq.Workplane):
            values = shape.vals()
            if not values or any(not isinstance(value, cq.Shape) for value in values):
                raise StudError('invalid_shape', f'Part {object_id} does not contain completed shapes.')
            shape = values[0] if len(values) == 1 else cq.Compound.makeCompound(values)
        if not isinstance(shape, cq.Shape) or not shape.Solids() or not shape.isValid():
            raise StudError('invalid_shape', f'Part {object_id} is not a valid completed solid.')
        snapshot = shape.copy()
        location = location or cq.Location()
        world = self._parent_location(parent) * location
        started = time.perf_counter()
        native = io.BytesIO()
        snapshot.exportBrep(native)
        native_bytes = native.getvalue()
        settings = {**unit_defaults(self.units),**(self.context['settings'] if self.context else {})}
        runtime = self.context['runtime']['id'] if self.context else cq.__version__
        mesh_settings={key:settings.get(key,.1) for key in ('linear_tolerance','angular_tolerance')}
        shape_key = digest(dict(brep=digest(native_bytes), runtime=runtime, units=self.units, settings=mesh_settings))
        self.timings['archive_seconds'] += time.perf_counter() - started
        if shape_key not in self.assets:
            asset = dict(key=shape_key, native=f'assets/{shape_key}.brep', mesh=f'assets/{shape_key}.mesh',
                         native_sha256=digest(native_bytes), units=self.units,bounds=shape_bounds(snapshot))
            if self.context:
                directory = self.context['directory']
                atomic_write(directory / asset['native'], native_bytes)
                started = time.perf_counter()
                vertices, triangles = snapshot.tessellate(settings.get('linear_tolerance', 0.1),
                                                         settings.get('angular_tolerance', 0.1))
                coordinates = [v for point in vertices for v in point.toTuple()]
                indices = [i for triangle in triangles for i in triangle]
                mesh = (struct.pack('<8sII', b'STUDMESH', len(vertices), len(triangles)) +
                        struct.pack(f'<{len(coordinates)}f', *coordinates) +
                        struct.pack(f'<{len(indices)}I', *indices))
                atomic_write(directory / asset['mesh'], mesh)
                asset.update(mesh_sha256=digest(mesh), vertices=len(vertices), triangles=len(triangles))
                self.timings['tessellation_seconds'] += time.perf_counter() - started
            self.assets[shape_key] = asset
        obj = dict(id=object_id, label=label or object_id, parent=parent, shape_key=shape_key,
                   mark=mark or 'P-' + digest(object_id.encode())[:8].upper(),
                   shape_digest=digest(native_bytes),
                   local_placement=location_matrix(location), placement=location_matrix(world),
                   bounds=shape_bounds(snapshot.located(world * snapshot.location())),
                   material=material, blank=deepcopy(blank), color=color, lineage=deepcopy(lineage),
                   volume=snapshot.Volume(), provenance=self._provenance())
        if any(old['mark'] == obj['mark'] and old['id'] != object_id for old in self.objects.values()):
            raise StudError('duplicate_id', 'Part marks must be unique; provide an explicit mark.', references=[object_id])
        # Replacing an object never silently preserves references to old faces.
        if replace:
            self.references = {key: value for key, value in self.references.items() if value['object_id'] != object_id}
        self.objects[object_id] = obj
        self.shapes[object_id] = dict(local=snapshot, world=snapshot.moved(world), location=world)
        publication = dict(operation='replace' if replace else 'add', object=obj, asset=self.assets[shape_key])
        if self._batch is not None:
            self._batch.append(publication)
        elif self.context:
            self.context['callback']('part_batch', [publication])
        return object_id

    @contextmanager
    def batch(self):
        if self._batch is not None:
            raise StudError('nested_batch', 'Publish one coherent group per batch.')
        registries = ('objects', 'shapes', 'assets', 'references', 'assemblies', 'requirements',
                      'demands', 'drawings', 'dimensions', 'steps', 'connections', 'expectations')
        previous = {name: getattr(self, name).copy() for name in registries}
        notes = self.notes[:]
        self._batch = []
        try:
            yield self
            if self.context and self._batch:
                self.context['callback']('part_batch', self._batch)
        except BaseException:
            for name, value in previous.items():
                setattr(self, name, value)
            self.notes[:] = notes
            raise
        finally:
            self._batch = None

    def reference(self, object_id, name, *, point=None, axis=None, plane=None):
        if object_id not in self.objects:
            raise StudError('unresolved_reference', f'Unknown part: {object_id}')
        key = f'{object_id}:{name}'
        self._unique(self.references, key)
        definitions = {k: v for k, v in [('point', point), ('axis', axis), ('plane', plane)] if v is not None}
        if len(definitions) != 1:
            raise StudError('invalid_reference', 'Declare exactly one point, axis, or plane.')
        kind, value = next(iter(definitions.items()))
        self.references[key] = dict(id=key, object_id=object_id, name=name, kind=kind, value=deepcopy(value))
        encoded(self.references[key])
        return key

    def requirement(self, requirement_id, kind, targets, *, threshold=0, units=None,
                    tolerance=None, explanation='', **policy):
        self._unique(self.requirements, requirement_id)
        units=units or requirement_units(self.units,kind)
        tolerance=unit_defaults(self.units)['query_tolerance'] if tolerance is None else tolerance
        self.requirements[requirement_id] = dict(id=requirement_id, kind=kind, targets=list(targets),
            threshold=threshold, units=units, tolerance=tolerance, explanation=explanation, policy=policy)
        return requirement_id

    def demand(self, demand_id, *, product_id, specification, object_ids, quantity=None,
               unit='each', purchase_unit='each', pack_size=1, stock_lengths=None,
               cuts=None, sheets=None, unresolved=None, **details):
        self._unique(self.demands, demand_id)
        if (unit in ('in','mm') and unit!=self.units) or any(
                record.get('length_unit',self.units)!=self.units for record in (specification,details)):
            raise StudError('unit_mismatch','Material dimensions must use the project units; no stock conversion is implicit.')
        specification={**specification,'length_unit':self.units}
        details.pop('length_unit',None)
        self.demands[demand_id] = dict(id=demand_id, product_id=product_id, specification=specification,
            object_ids=list(object_ids), quantity=quantity, unit=unit, purchase_unit=purchase_unit,
            pack_size=pack_size, stock_lengths=stock_lengths, cuts=cuts, sheets=sheets,
            unresolved=unresolved or [],length_unit=self.units, **details)
        return demand_id

    def dimension(self, dimension_id, start, end, *, label='', measurement='distance', **layout):
        self._unique(self.dimensions, dimension_id)
        self.dimensions[dimension_id] = dict(id=dimension_id, start=start, end=end, label=label,
                                             measurement=measurement, **layout)
        return dimension_id

    def drawing(self, drawing_id, *, label=None, objects=None, direction=(0, -1, 0),
                up=(0, 0, 1), dimensions=None, section=None, **layout):
        self._unique(self.drawings, drawing_id)
        self.drawings[drawing_id] = dict(id=drawing_id, label=label or drawing_id, objects=objects,
            direction=list(direction), up=list(up), dimensions=dimensions or [], section=section, **layout)
        return drawing_id

    def connection(self, connection_id, *, parts, description, **details):
        self._unique(self.connections, connection_id)
        self.connections[connection_id] = dict(id=connection_id, parts=list(parts), description=description, **details)
        return connection_id

    def expect(self, expectation_id, *, parts, requirements=(), connections=()):
        """Retain an assembly's expected inventory independently of its output."""
        self._unique(self.expectations,expectation_id)
        self.expectations[expectation_id]=dict(id=expectation_id,parts=list(parts),
            requirements=list(requirements),connections=list(connections))
        return expectation_id

    def step(self, step_id, text, *, parts, prerequisites=None, connections=None, view=None, exploded=None):
        self._unique(self.steps, step_id)
        self.steps[step_id] = dict(id=step_id, text=text, parts=list(parts), prerequisites=prerequisites or [],
            connections=connections or [], view=view, exploded=exploded or {})
        return step_id

    def export(self):
        return dict(name=self.name, units=self.units, objects=list(self.objects.values()),
            assemblies=[{k: v for k, v in item.items() if not k.startswith('_')} for item in self.assemblies.values()],
            assets=self.assets, references=self.references, requirements=list(self.requirements.values()),
            demands=list(self.demands.values()), dimensions=list(self.dimensions.values()),
            drawings=list(self.drawings.values()), steps=list(self.steps.values()),
            connections=list(self.connections.values()), expectations=list(self.expectations.values()),
            notes=self.notes, timings=self.timings)
