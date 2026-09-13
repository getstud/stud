"""Measured geometric evidence. Bounds are never the final fit/collision oracle."""
import math
import time

import cadquery as cq

from .cad import point_at
from .contracts import StudError
from .units import requirement_units


def resolve_point(model, reference):
    if isinstance(reference, (list, tuple)) and len(reference) == 3:
        return list(reference)
    entry = model.references.get(reference)
    if not entry or entry['object_id'] not in model.shapes:
        raise StudError('unresolved_reference', f'Named reference is missing: {reference}', references=[reference])
    if entry['kind'] != 'point':
        raise StudError('unsupported_measurement', f'Expected a point reference: {reference}')
    return point_at(model.shapes[entry['object_id']]['location'], entry['value'])


def contact_area(first, second, tolerance, angular_tolerance=1e-4, direction=None):
    """Area shared by opposing planar faces; distance alone is not bearing."""
    area = 0.0
    for face_a in first.Faces():
        if face_a.geomType() != 'PLANE':
            continue
        normal_a = face_a.normalAt()
        projected = max(0.0, normal_a.dot(direction)) if direction is not None else 1.0
        if projected <= angular_tolerance:
            continue
        for face_b in second.Faces():
            if face_b.geomType() != 'PLANE':
                continue
            if normal_a.dot(face_b.normalAt()) > -1 + angular_tolerance:
                continue
            # Intersect the real coplanar faces. Nearby disjoint faces do not
            # become a claimed contact just because a broad-phase box touches.
            if face_a.distance(face_b) <= tolerance:
                common = face_a.intersect(face_b, tol=tolerance)
                area += projected * sum(face.Area() for face in common.Faces())
    return area


def panel_edge_support(model, part_id, support_ids, direction_local):
    """Unbacked perimeter length on the actual panel face, including cutouts.

    Only coplanar opposing contact faces count. Subtracting their intersection
    with each native edge checks every edge interval, not selected sample points.
    """
    entry=model.shapes[part_id]
    origin=point_at(entry['location'],[0,0,0])
    end=point_at(entry['location'],direction_local)
    direction=cq.Vector(*[a-b for a,b in zip(end,origin)]).normalized()
    faces=[face for face in entry['world'].Faces() if face.geomType()=='PLANE' and face.normalAt().dot(direction)>1-1e-5]
    if not faces:raise StudError('unsupported_measurement','The requested panel backing face is not planar.')
    edges=[]
    for face in faces:
        contacts=[]
        for key in support_ids:
            for backing in model.shapes[key]['world'].Faces():
                if backing.geomType()=='PLANE' and backing.normalAt().dot(direction)<-1+1e-5 and face.distance(backing)<1e-5:
                    contacts.extend(face.intersect(backing).Faces())
        for edge in face.Edges():
            remaining=edge
            for contact in contacts:
                if not remaining.Edges():break
                remaining=remaining.cut(contact)
            missing=sum(e.Length() for e in remaining.Edges())
            edges.append(dict(length=edge.Length(),unbacked=missing,center=list(edge.Center().toTuple())))
    return sum(edge['unbacked'] for edge in edges),edges


def _requirement_units(model,requirement):
    kind = requirement['kind']
    units=requirement_units(model.units,kind)
    if requirement.get('units',units)!=units:
        raise StudError('unit_mismatch',f'{kind} requires {units} in this project.')
    return units


def measure_requirement(model, requirement):
    kind = requirement['kind']
    units=_requirement_units(model,requirement)
    targets = requirement['targets']
    threshold, tolerance = float(requirement['threshold']), float(requirement['tolerance'])
    if not math.isfinite(threshold) or not math.isfinite(tolerance) or tolerance < 0:
        raise StudError('invalid_requirement', 'Threshold and nonnegative tolerance must be finite.')
    if kind in ('length', 'point_distance'):
        if len(targets) != 2:
            raise StudError('invalid_requirement', 'Point distance requires two targets.')
        a, b = (resolve_point(model, target) for target in targets)
        value = math.dist(a, b)
        return value, abs(value - threshold) <= tolerance, dict(start=a, end=b)
    for target in targets:
        if target not in model.shapes:
            raise StudError('unresolved_reference', f'Part is missing: {target}', references=[target])
    if kind == 'panel_edge_system':
        from .panel_edges import edge_intervals
        policy=requirement.get('policy',{})
        supports=policy.get('supports',[]);mates=policy.get('mates',[])
        if not targets or set(targets)!={targets[0],*supports,*mates} or targets[0] in supports+mates:
            raise StudError('invalid_requirement','Panel edge system targets must include exactly the panel, supports and mates.')
        missing,edges=edge_intervals(model,targets[0],supports,mates)
        value=sum(e.Length() for e in missing)
        return value,value<=threshold+tolerance,dict(operation='native perimeter minus wood contact and compatible factory joints',units=units,edges=edges)
    if kind == 'panel_edge_support':
        if len(targets)<2:raise StudError('invalid_requirement','Panel backing requires a panel and named supporting members.')
        direction=requirement.get('policy',{}).get('direction_local')
        if not isinstance(direction,(list,tuple)) or len(direction)!=3 or not all(math.isfinite(v) for v in direction) or math.dist(direction,[0,0,0])<1e-9:
            raise StudError('invalid_requirement','Panel backing requires a nonzero local direction toward its supports.')
        value,edges=panel_edge_support(model,targets[0],targets[1:],direction)
        return value,value<=threshold+tolerance,dict(operation='native perimeter minus opposing contact faces',units=units,edges=edges)
    if kind == 'solid_valid':
        if not targets:raise StudError('invalid_requirement','Solid validity requires at least one target.')
        valid=all(model.shapes[t]['world'].isValid() for t in targets)
        return int(valid), valid, {'operation': 'OCCT validity'}
    if kind == 'stock_fit':
        if len(targets) != 1:
            raise StudError('invalid_requirement', 'Stock fit requires one part in its stock frame.')
        obj = model.objects[targets[0]]
        blank = obj.get('blank')
        if not blank or not blank.get('size'):
            raise StudError('unresolved_reference', 'Stock blank dimensions are missing.', references=targets)
        size = blank['size']
        origin = blank.get('origin', [0, 0, 0])
        stock = cq.Workplane('XY').box(*size, centered=(False, False, False)).translate(origin).val()
        outside = model.shapes[targets[0]]['local'].cut(stock).Volume()
        return outside, outside <= tolerance ** 3, dict(operation='solid minus blank', blank=blank, units=units)
    if kind == 'collision_free':
        if not targets:
            raise StudError('invalid_requirement','Interference checking requires physical parts.')
        pairs=[];value=0.0;queried=0
        allowed={frozenset(pair) for pair in requirement.get('policy',{}).get('allowed_pairs',[])}
        for index,left in enumerate(targets):
            a=model.objects[left]['bounds']
            for right in targets[index+1:]:
                if frozenset((left,right)) in allowed:
                    continue
                b=model.objects[right]['bounds']
                # Bounds only reject impossible intersections. Any candidate
                # is resolved with the real native solids, including holes.
                if any(min(a['max'][i],b['max'][i])-max(a['min'][i],b['min'][i])<=1e-7 for i in range(3)):
                    continue
                queried+=1
                volume=model.shapes[left]['world'].intersect(model.shapes[right]['world']).Volume()
                if volume>tolerance**3:
                    value+=volume;pairs.append({'parts':[left,right],'volume':volume})
        return value,value<=threshold+tolerance**3,dict(operation='OCCT common solid volumes',units=units,pairs=pairs,queried_pairs=queried)
    if len(targets) != 2:
        raise StudError('invalid_requirement', f'{kind} requires exactly two target parts.')
    a, b = (model.shapes[target]['world'] for target in targets)
    if kind in ('clearance', 'distance'):
        value = a.distance(b)
        passed = value + tolerance >= threshold if kind == 'clearance' else abs(value - threshold) <= tolerance
        return value, passed, dict(operation='OCCT minimum solid distance')
    if kind == 'collision':
        value = a.intersect(b).Volume()
        return value, value <= threshold + tolerance ** 3, dict(operation='OCCT common solid volume', units=units)
    if kind in ('contact', 'support'):
        policy=requirement.get('policy',{})
        direction=None
        if kind=='support':
            values=policy.get('direction',[0,0,-1])
            if not isinstance(values,(tuple,list)) or len(values)!=3 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in values) or math.dist(values,[0,0,0])<1e-9:
                raise StudError('invalid_requirement','Bearing direction must be a finite nonzero world-space vector.')
            direction=cq.Vector(*values).normalized()
            region=policy.get('region_local')
            if region is not None:
                try:
                    lo,hi=region['min'],region['max']
                    valid=len(lo)==len(hi)==3 and all(math.isfinite(v) for v in (*lo,*hi)) and all(x<y for x,y in zip(lo,hi))
                except (TypeError,KeyError,ValueError):valid=False
                if not valid:raise StudError('invalid_requirement','A bearing region needs finite local min/max bounds with positive extents.')
                clip=cq.Workplane('XY').box(*[y-x for x,y in zip(lo,hi)],centered=(False,False,False)).translate(lo).val()
                a=a.intersect(clip.moved(model.shapes[targets[0]]['location']))
                if not a.Solids():return 0,False,dict(operation='empty local bearing region',units=units)
        area = contact_area(a, b, tolerance, direction=direction)
        return area, area+tolerance**2 >= threshold and area > 0, dict(operation='opposing planar contact projected perpendicular to bearing direction' if direction else 'opposing planar face intersection',
            direction=list(direction.toTuple()) if direction else None,distance=a.distance(b), units=units)
    raise StudError('unsupported_measurement', f'Unsupported requirement: {kind}')


_native_measure_requirement=measure_requirement


def check_model(model, *, cache_path=None, reuse=True):
    started = time.perf_counter()
    findings, covered = [], set()
    timings={}
    from .query_cache import QueryCache
    cache=QueryCache(cache_path) if reuse and measure_requirement is _native_measure_requirement else None
    for requirement in model.requirements.values():
        finding = dict(requirement_id=requirement['id'], kind=requirement['kind'], targets=requirement['targets'],
            expected=requirement['threshold'], units=requirement['units'], tolerance=requirement['tolerance'],
            explanation=requirement['explanation'], measured=None, evidence=None)
        query_started=time.perf_counter()
        cached=None
        try:
            _requirement_units(model,requirement)
            key=cache.key(model,requirement) if cache else None
            cached=cache.get(key) if cache and key else None
            if cached is None:
                value, passed, evidence = measure_requirement(model, requirement)
                if cache:cache.put(key,(value,passed,evidence))
            else:
                value,passed,evidence=cached
            finding.update(status='passed' if passed else 'failed', measured=value, evidence=evidence,
                           units=evidence.get('units', requirement['units']))
            for target in requirement['targets']:
                covered.add(model.references[target]['object_id'] if target in model.references else target)
        except StudError as error:
            status = {'unresolved_reference': 'unresolved', 'unsupported_measurement': 'unsupported'}.get(error.category, 'execution_failed')
            finding.update(status=status, error=error.as_dict())
        except Exception as error:
            finding.update(status='execution_failed', error={'category': 'geometric_operation_failed', 'message': str(error)})
        timing=timings.setdefault(requirement['kind'],dict(count=0,elapsed_seconds=0.0))
        timing['count']+=1;timing['elapsed_seconds']+=time.perf_counter()-query_started
        if cached is not None:timing['cache_hits']=timing.get('cache_hits',0)+1
        findings.append(finding)
    uncovered = sorted(set(model.objects) - covered)
    counts = {status: sum(f['status'] == status for f in findings) for status in
              ('passed', 'failed', 'unresolved', 'unsupported', 'execution_failed')}
    if cache:cache.save()
    return dict(findings=findings, counts=counts, coverage=dict(requested=len(findings),
                evaluated=counts['passed'] + counts['failed'], uncovered_objects=uncovered,
                complete=bool(findings) and not uncovered and not any(counts[k] for k in ('unresolved', 'unsupported', 'execution_failed'))),
                all_passed=bool(findings) and counts['passed'] == len(findings) and not uncovered,
                elapsed_seconds=time.perf_counter() - started,timings=timings)
