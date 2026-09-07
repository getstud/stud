"""Development checks for declared model relationships; no structural certification.
Run python3 validate.py [--json] [--strict] [--model path].
"""
import argparse
import json
import math
from collections import Counter
from itertools import combinations
from pathlib import Path
from validation_rules import KINDS, Context, evaluate, coverage

EPS = 1e-6


def angle(p): return math.radians(p.get('rotation',[0,0,0])[0])

def face_bounds(p,face):
    if 'profile' in p or abs(angle(p))<EPS:
        return [(o,o+d) for o,d in zip(p['origin'],p['size'])]
    t=angle(p);c=math.cos(t);sn=math.sin(t)
    center=[o+d/2 for o,d in zip(p['origin'],p['size'])]
    dz=p['size'][2]/2*(1 if face=='top' else -1)
    ys=[center[1]+dy*c-dz*sn for dy in (-p['size'][1]/2,p['size'][1]/2)]
    zs=[center[2]+dy*sn+dz*c for dy in (-p['size'][1]/2,p['size'][1]/2)]
    return [(p['origin'][0],p['origin'][0]+p['size'][0]),(min(ys),max(ys)),(min(zs),max(zs))]

def bounds(p):
    a,b=face_bounds(p,'top'),face_bounds(p,'bottom')
    return [(min(x[0],y[0]),max(x[1],y[1])) for x,y in zip(a,b)]

def uncut_surface(p, face, y):
    if 'profile' in p:
        a,b=p['profile'][face]
        return p['origin'][2]+a+(b-a)*(y-p['origin'][1])/p['size'][1]
    t=angle(p);c=math.cos(t)
    cy=p['origin'][1]+p['size'][1]/2;cz=p['origin'][2]+p['size'][2]/2
    return cz+math.tan(t)*(y-cy)+(1 if face=='top' else -1)*p['size'][2]/(2*c)

def surface(p,face,y):
    z=uncut_surface(p,face,y)
    if face=='bottom':
        for seat in p.get('seats',[]):
            if seat['y'][0]-EPS<=y<=seat['y'][1]+EPS: z=max(z,seat['z'])
    return z

def segments(a,b,lo,hi):
    cuts=sorted(set([lo,hi]+[v for p in (a,b) for seat in p.get('seats',[]) for v in seat['y'] if lo<v<hi]))
    return [(a,b) for a,b in zip(cuts,cuts[1:]) if b-a>EPS]

def contact(upper, lower):
    ub,lb=face_bounds(upper,'bottom'),face_bounds(lower,'top')
    spans=[(max(ub[i][0],lb[i][0]),min(ub[i][1],lb[i][1])) for i in (0,1)]
    if not all(b-a>EPS for a,b in spans): return False
    return all(abs(surface(upper,'bottom',y)-surface(lower,'top',y))<EPS
               for lo,hi in segments(upper,lower,*spans[1]) for y in (lo+(hi-lo)*.00001,hi-(hi-lo)*.00001))

def unrotated_bounds(p,t):
    # Put boxes sharing the same pitch into a common orthogonal coordinate frame.
    c=math.cos(t);sn=math.sin(t)
    x,y,z=[o+d/2 for o,d in zip(p['origin'],p['size'])]
    center=[x,y*c+z*sn,-y*sn+z*c]
    return [(v-d/2,v+d/2) for v,d in zip(center,p['size'])]

def overlaps(a,b):
    if not a.get('seats') and not b.get('seats') and 'profile' not in a and 'profile' not in b and abs(angle(a)-angle(b))<EPS:
        aa,bb=unrotated_bounds(a,angle(a)),unrotated_bounds(b,angle(a))
        return all(min(aa[j][1],bb[j][1])-max(aa[j][0],bb[j][0])>EPS for j in range(3))
    # Profiles have vertical side faces. Pitched boxes have sloped end faces;
    # use the common full-depth Y interval, never their inflated bounding boxes.
    aa,bb=bounds(a),bounds(b)
    if min(aa[0][1],bb[0][1])-max(aa[0][0],bb[0][0])<=EPS: return False
    intervals=[]
    for p in (a,b):
        top,bottom=face_bounds(p,'top'),face_bounds(p,'bottom')
        intervals.append((max(top[1][0],bottom[1][0]),min(top[1][1],bottom[1][1])))
    lo=max(i[0] for i in intervals);hi=min(i[1] for i in intervals)
    if hi-lo<=EPS:return False
    # Split at notch boundaries before solving each pair of linear inequalities.
    for start,end in segments(a,b,lo,hi):
        left,right=start+(end-start)*.00001,end-(end-start)*.00001
        for upper,lower in ((a,b),(b,a)):
            f0=surface(upper,'top',left)-surface(lower,'bottom',left)-EPS
            f1=surface(upper,'top',right)-surface(lower,'bottom',right)-EPS
            if max(f0,f1)<=0: break
            if min(f0,f1)<0:
                cut=left+(right-left)*(-f0)/(f1-f0)
                if f0<0:left=cut
                else:right=cut
        else:
            if right-left>EPS:return True
    return False


def validate(model):
    findings = []
    parts = {p['id']: p for p in model['parts']}
    active_rule = {}
    def emit(status, rule, ids, message):
        findings.append(dict(status=status, rule=rule, parts=ids, message=message, **active_rule))
    duplicate_ids=[pid for pid,count in Counter(p['id'] for p in model['parts']).items() if count>1]
    if duplicate_ids:
        emit('FAIL','model',duplicate_ids,'Duplicate part IDs in exported model.')
        return findings
    spec = model.get('validation')
    if not spec:
        emit('UNVERIFIED', 'coverage', [], 'No validation relationships declared.')
        return findings
    if spec.get('version') != 1:
        emit('FAIL', 'coverage', [], 'Unsupported validation contract version.')
        return findings

    def get(ids, rule):
        missing = [i for i in ids if i not in parts]
        if missing:
            emit('FAIL', rule, missing, 'Required model part is missing.')
            return None
        ps = [parts[i] for i in ids]
        if any(any(abs(r)>EPS for r in p.get('rotation',[0,0,0])[1:]) or ('profile' in p and abs(angle(p))>EPS) for p in ps):
            emit('UNVERIFIED', rule, ids, 'Rotated geometry requires a transformed-solid check.')
            return None
        return ps

    if not isinstance(spec.get('rules', []), list):
        emit('FAIL', 'configuration', [], 'rules must be a list.')
        return findings
    requirements = spec.get('requirements', [])
    if (not isinstance(requirements, list) or any(
            not isinstance(r, dict) or any(not isinstance(r.get(key), str) or not r[key].strip()
                                         for key in ('id', 'rule_id', 'component', 'label'))
            or not isinstance(r.get('parts', []), list) for r in requirements)):
        emit('FAIL', 'configuration', [], 'requirements need stable IDs, rule IDs, components, labels and part lists.')
        return findings
    if len({r['id'] for r in requirements}) != len(requirements):
        emit('FAIL', 'configuration', [], 'Duplicate requirement IDs.')
        return findings
    context = Context(model)
    automatic = spec.get('automatic', [])
    if not isinstance(automatic, list) or any(k not in ('solid_collision', 'stock_fit') for k in automatic):
        emit('FAIL', 'configuration', [], 'automatic supports solid_collision and stock_fit only.')
        return findings
    rules = [{'kind': kind, 'parts': list(parts)} for kind in automatic] + spec.get('rules', [])
    if any(not isinstance(r, dict) or ('id' in r and (not isinstance(r['id'], str) or not r['id'].strip())) for r in rules):
        emit('FAIL', 'configuration', [], 'Rules must be objects with nonempty string IDs when supplied.')
        return findings
    if not spec.get('rules'):
        emit('UNVERIFIED', 'coverage', [], 'No geometry rules declared.')
    named_ids = [r.get('id') for r in rules if isinstance(r, dict) and r.get('id')]
    duplicates = {rid for rid, count in Counter(named_ids).items() if count > 1}
    for rid in sorted(duplicates):
        findings.append(dict(status='FAIL', rule='configuration', rule_id=rid,
                             rule_id_explicit=True, parts=[], message=f'Duplicate rule ID: {rid}'))
    for index, rule in enumerate(rules):
        active_rule = {'rule_id': rule.get('id', f'rule-{index}'), 'rule_id_explicit': 'id' in rule}
        if 'source' in rule:
            active_rule['source'] = rule['source']
        try:
            if rule.get('id') in duplicates:
                continue
            if 'scope' in rule:
                if not isinstance(rule['scope'], str) or not rule['scope'].strip():
                    raise ValueError('scope must be a nonempty validation scope name')
                selected = [p['id'] for p in model['parts']
                            if rule['scope'] in p.get('validation_scopes', [])]
                rule = {**rule, 'parts': list(dict.fromkeys([*rule.get('parts', []), *selected]))}
            kind, ids = rule['kind'], rule.get('parts', [])
            if kind in KINDS:
                if not ids: raise ValueError('Rule scope must select at least one part')
                measured = evaluate(context, rule)
                for finding in measured:
                    finding.update(active_rule)
                findings.extend(measured)
                continue
        except (KeyError, ValueError, TypeError, IndexError, ZeroDivisionError) as error:
            emit('FAIL', 'configuration', [], f'Rule {index}: {error}')
            findings[-1]['rule_id'] = rule.get('id', f'rule-{index}')
            if 'source' in rule:
                findings[-1]['source'] = rule['source']
            continue
        ps = get(ids, kind)
        if ps is None:
            continue
        ok = True
        detail = ''
        if kind == 'bearing':
            upper, *supports = ps
            touching = [p for p in supports if contact(upper, p)]
            ok = len(touching) >= rule.get('minimum', len(supports))
            detail = f"{len(touching)}/{len(supports)} declared supports have bearing contact; required {rule.get('minimum', len(supports))}."
        elif kind == 'seat_alignment':
            block,rafter=ps
            lo,hi=face_bounds(block,'bottom')[1]
            ok=all(abs(surface(block,'bottom',y)-surface(rafter,'bottom',y))<EPS for y in (lo,(lo+hi)/2,hi))
            detail='Wall-line blocking underside must align with the adjacent rafter seat plane.'
        elif kind == 'rafter_seats':
            rafter,*plates=ps
            ok=True
            for plate in plates:
                pb=bounds(plate);lo,hi=pb[1]
                z=surface(plate,'top',(lo+hi)/2)
                matches=[seat for seat in rafter.get('seats',[]) if seat['y'][0]<=lo+EPS and seat['y'][1]>=hi-EPS and abs(seat['z']-z)<EPS]
                depth=max(z-uncut_surface(rafter,'bottom',y) for y in (lo,hi))*math.cos(angle(rafter))
                tapers=bool(matches) and all(abs(uncut_surface(rafter,'bottom',seat['y'][0])-seat['z'])<EPS and abs(seat['y'][1]-seat['y'][0]-rule['bearing_length'])<EPS for seat in matches)
                ok=ok and tapers and contact(rafter,plate) and hi-lo>=rule['bearing_length']-EPS and 0<=depth<=rule['max_depth']+EPS
            detail='Each level wall requires a full-width horizontal seat within the project notch-depth limit; connection and code approval are separate.'
        elif kind == 'joist_end_restraint':
            joist, front, back = ps
            axis=rule.get('axis',1)
            cross=1-axis
            if any(abs(angle(p)-angle(joist))>EPS for p in ps):
                emit('FAIL',kind,ids,'Rims and joist must share the declared frame pitch.');continue
            jb=unrotated_bounds(joist,angle(joist))
            ok=True
            for end,rim in enumerate((front,back)):
                rb=unrotated_bounds(rim,angle(joist))
                ok = ok and abs(jb[axis][end]-rb[axis][1-end]) < EPS
                ok = ok and rb[cross][0] <= jb[cross][0]+EPS and rb[cross][1] >= jb[cross][1]-EPS
                ok = ok and rb[2][0] <= jb[2][0]+EPS and rb[2][1] >= jb[2][1]-EPS
            detail = 'Both joist ends must meet declared full-depth rims across their full end faces; fastening is separate.'
        elif kind == 'panel_edge_bearing':
            panel,*supports=ps
            pb=bounds(panel)
            width=rule['bearing_width']
            gaps=[]
            for axis in (0,1):
                along=1-axis
                for end in (0,1):
                    width=rule.get('edge_widths',{}).get(f'{axis}:{end}',rule['bearing_width'])
                    edge=pb[axis][end]
                    band=(edge,edge+width) if end==0 else (edge-width,edge)
                    intervals=[]
                    for support in supports:
                        sb=face_bounds(support,'top')
                        if sb[axis][0] > band[0]+EPS or sb[axis][1] < band[1]-EPS:
                            continue
                        a=max(pb[along][0],sb[along][0]);b=min(pb[along][1],sb[along][1])
                        if b-a <= EPS: continue
                        ys=(a,b) if along==1 else band
                        if all(abs(surface(panel,'bottom',y)-surface(support,'top',y)) < EPS for y in ys):
                            intervals.append((a,b))
                    cursor=pb[along][0]
                    for a,b in sorted(intervals):
                        if a > cursor+EPS: break
                        cursor=max(cursor,b)
                    if cursor < pb[along][1]-EPS: gaps.append(f'{"XY"[axis]} {"min" if end==0 else "max"}')
            ok=not gaps
            detail=f"Project detail requires continuous edge bearing: default {rule['bearing_width']:g} inches; overrides {rule.get('edge_widths',{})}."
            if gaps: detail+=' Incomplete edges: '+', '.join(gaps)+'.'
        elif kind == 'plate_end_bearing':
            plate,*supports=ps
            axis=rule['axis'];cross=1-axis;pb=face_bounds(plate,'bottom')
            width=rule['bearing_length']
            missing=[]
            for end in (0,1):
                band=(pb[axis][0],pb[axis][0]+width) if end==0 else (pb[axis][1]-width,pb[axis][1])
                def supports_end(stud):
                    sb=face_bounds(stud,'top')
                    return (contact(plate,stud) and sb[axis][0]<=band[0]+EPS and sb[axis][1]>=band[1]-EPS
                            and sb[cross][0]<=pb[cross][0]+EPS and sb[cross][1]>=pb[cross][1]-EPS)
                if not any(supports_end(stud) for stud in supports): missing.append(str(end))
            ok=not missing
            detail=f'Plate requires {width:g}-inch bearing at both ends across its full width.'
            if missing: detail+=' Missing ends: '+', '.join(missing)+'.'
        elif kind == 'edgewise_header':
            axis = rule.get('thickness_axis', 1)
            ok = all(p['size'][2] > p['size'][axis]+EPS for p in ps)
            detail = 'Header plies must stand on edge; capacity is checked separately.'
        elif kind == 'corner_lap':
            cap, *lower = ps
            ok = all(contact(cap, p) for p in lower)
            detail = 'Upper cap must bear across both adjoining lower top plates.'
        elif kind == 'opening_edge':
            p = ps[0]
            axis = rule['span_axis']
            bb = bounds(p)
            span = rule['span']
            face = surface(p, rule['face'], p['origin'][1])
            ok = (bb[axis][0] <= span[0]+EPS and bb[axis][1] >= span[1]-EPS
                  and abs(face-rule['elevation']) < EPS)
            detail = 'Opening edge must cover its declared span at the clear-opening boundary.'
        elif kind == 'roof_slope':
            p = ps[0]
            fall = surface(p, 'top', p['origin'][1])-surface(p, 'top', p['origin'][1]+p['size'][1])
            ok = fall/p['size'][1] >= rule['minimum_slope']-EPS
            detail = f"Downhill slope {fall/p['size'][1]:.5f} in/in; project minimum {rule['minimum_slope']:.5f}."
        elif kind == 'level_top':
            ok = all(abs(surface(p, 'top', p['origin'][1])-surface(p, 'top', p['origin'][1]+p['size'][1])) < EPS for p in ps)
            detail = 'Deck support tops must be level.'
        elif kind == 'non_overlap':
            for a, b in combinations(ps, 2):
                if overlaps(a,b):
                    emit('FAIL', kind, [a['id'], b['id']], 'Framing solids overlap internally.')
                    ok = False
            if ok:
                emit('PASS', kind, ids, 'No internal overlaps among declared framing parts.')
            continue
        else:
            emit('FAIL', kind, ids, 'Unknown validation rule.')
            continue
        emit('PASS' if ok else 'FAIL', kind, ids, detail)
    active_rule = {}
    for requirement in requirements:
        if not any(f.get('rule_id') == requirement['rule_id'] and f.get('rule_id_explicit') for f in findings):
            findings.append(dict(status='UNVERIFIED', rule='requirement',
                                 rule_id=requirement['rule_id'], rule_id_explicit=True,
                                 parts=requirement.get('parts', []),
                                 message=f"{requirement['component']}: {requirement['label']} has no evaluated check."))
    for item in spec.get('unverified', []):
        emit('UNVERIFIED', item['rule'], item.get('parts', []), item['message'])
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path.cwd(), help='Project directory containing design.py.')
    parser.add_argument('--model', type=Path, help='Validate an exported JSON model instead of compiling current Python.')
    parser.add_argument('--json', action='store_true', help='Print machine-readable findings, including passes.')
    parser.add_argument('--strict', action='store_true', help='Also exit nonzero for warnings and unverified items.')
    args = parser.parse_args()
    try:
        if args.model:
            model = json.loads(args.model.read_text())
        else:
            from build import compile_project
            model = compile_project(args.project)
        findings = validate(model)
    except (ValueError, KeyError, TypeError, OSError) as e:
        findings = [dict(status='FAIL', rule='model', parts=[], message=str(e))]
    counts = Counter(f['status'] for f in findings)
    if args.json:
        print(json.dumps(dict(counts=dict(counts), findings=findings, coverage=coverage(model,findings) if 'model' in locals() else None), indent=2))
    else:
        for f in findings:
            if f['status'] != 'PASS':
                print(f"{f['status']} {f['rule']} [{', '.join(f['parts']) or 'project'}]: {f['message']}")
        print(f"{counts['PASS']} passed; {counts['FAIL']} failed; {counts['WARNING']} warnings; {counts['UNVERIFIED']} unverified.")
    return 1 if counts['FAIL'] else (2 if args.strict and (counts['UNVERIFIED'] or counts['WARNING']) else 0)


if __name__ == '__main__':
    raise SystemExit(main())
