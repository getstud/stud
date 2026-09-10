"""Reopen one immutable evaluated model without rerunning its Python source."""
import io
from pathlib import Path
from types import SimpleNamespace

import cadquery as cq
from OCP.gp import gp_Trsf

from .contracts import StudError, confined, digest, read_json, manifest_name
from .source import runtime_fingerprint
from .units import validate as validate_units


def location_from_matrix(matrix):
    transform = gp_Trsf()
    transform.SetValues(*(float(value) for row in matrix[:3] for value in row))
    return cq.Location(transform)


def load_model(directory, *, require_runtime=True, manifest_version=None, expected=None):
    directory = Path(directory)
    relative=manifest_name(manifest_version)
    path=confined(directory,relative)
    manifest = read_json(path)
    if not manifest:
        raise StudError('unavailable_artifact', 'The evaluated model manifest is missing.')
    validate_units(manifest.get('units'))
    if expected:
        required={key:expected[key] for key in ('project_id','source_id')}
        required['build_id']=expected.get('build_id',expected['id'])
        if any(manifest.get(key)!=value for key,value in required.items()):
            raise StudError('artifact_identity_mismatch','The archive does not match the requested project, source and build.',references=[required['build_id']])
        recorded=expected.get('manifest_hashes',{}).get(relative)
        if recorded and digest(path.read_bytes())!=recorded:
            raise StudError('unavailable_artifact','The immutable evaluated manifest has changed.',references=[relative])
        if manifest['runtime']['id']!=expected['runtime']['id']:
            raise StudError('artifact_identity_mismatch','The archive runtime does not match its recorded build.')
    if require_runtime and manifest['runtime']['id'] != runtime_fingerprint()['id']:
        raise StudError('unavailable_runtime', 'Native shape regeneration/query requires the recorded runtime.',
                        expected=manifest['runtime']['id'], current=runtime_fingerprint()['id'])
    shapes, loaded = {}, {}
    for obj in manifest['objects']:
        key = obj['shape_key']
        if key not in loaded:
            asset = manifest['assets'][key]
            if asset.get('units')!=manifest['units']:
                raise StudError('artifact_identity_mismatch','The shape archive units differ from the evaluated model.')
            file = confined(directory, asset['native'])
            if not file.is_file() or digest(file.read_bytes()) != asset['native_sha256']:
                raise StudError('unavailable_artifact', 'A native shape archive is missing or corrupt.', references=[obj['id']])
            loaded[key] = cq.Shape.importBrep(io.BytesIO(file.read_bytes()))
        local = loaded[key]
        location = location_from_matrix(obj['placement'])
        shapes[obj['id']] = dict(local=local, world=local.moved(location), location=location)
    model = SimpleNamespace(name=manifest['name'],units=manifest['units'], objects={o['id']:o for o in manifest['objects']},
                            assemblies={a['id']:a for a in manifest['assemblies']}, shapes=shapes,
                            references=manifest['references'], requirements={r['id']:r for r in manifest['requirements']})
    return model, manifest


def object_scope(model, scope):
    if scope is None:
        return list(model.objects)
    result = set()
    for target in scope:
        if target in model.objects:
            result.add(target)
        elif target in model.assemblies:
            for obj in model.objects.values():
                parent = obj['parent']
                while parent:
                    if parent == target:
                        result.add(obj['id'])
                        break
                    parent = model.assemblies[parent]['parent']
        else:
            raise StudError('unresolved_reference', f'Drawing object or assembly is missing: {target}')
    return sorted(result)
