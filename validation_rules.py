"""Measured geometric validation. No structural thresholds are inferred."""
import math
from itertools import combinations
import solid_geometry as geo

KINDS={'solid_collision','minimum_contact','face_alignment','opening_clearance','panel_support','stock_fit'}


def positive(value,name,allow_zero=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or (value<0 if allow_zero else value<=0):raise ValueError(f'{name} must be a finite '+('nonnegative' if allow_zero else 'positive')+' number')
    return value


def polygon_union_area(polygons):
    """Integrate interval unions between all polygon edge crossing events."""
    edges=[(a,b) for p in polygons for a,b in zip(p,p[1:]+p[:1]) if abs(a[0]-b[0])>geo.EPS]
    xs={v[0] for p in polygons for v in p}
    for (a,b),(c,d) in combinations(edges,2):
        ma=(b[1]-a[1])/(b[0]-a[0]);mb=(d[1]-c[1])/(d[0]-c[0])
        if abs(ma-mb)<geo.EPS:continue
        x=(c[1]-mb*c[0]-a[1]+ma*a[0])/(ma-mb)
        if max(min(a[0],b[0]),min(c[0],d[0]))<x<min(max(a[0],b[0]),max(c[0],d[0])):xs.add(x)
    def length(x):
        intervals=[]
        for polygon in polygons:
            ys=[]
            for a,b in zip(polygon,polygon[1:]+polygon[:1]):
                if min(a[0],b[0])<x<max(a[0],b[0]):ys.append(a[1]+(b[1]-a[1])*(x-a[0])/(b[0]-a[0]))
            if ys:intervals.append((min(ys),max(ys)))
        total=0;end=-math.inf
        for a,b in sorted(intervals):
            total+=max(0,b-max(a,end));end=max(end,b)
        return total
    xs=sorted(xs)
    # Within each event interval, union endpoints are linear functions.
    return sum((b-a)*length((a+b)/2) for a,b in zip(xs,xs[1:]))


class Context:
    def __init__(self,model):
        self.model=model;self.parts={p['id']:p for p in model['parts']};self.cache={};self.bound_cache={}
    def solid(self,pid):
        if pid not in self.cache:self.cache[pid]=geo.solids(self.parts[pid])
        return self.cache[pid]
    def bounds(self,pid):
        if pid not in self.bound_cache:self.bound_cache[pid]=geo.bounds(self.solid(pid))
        return self.bound_cache[pid]


def evaluate(context,rule):
    kind=rule['kind'];ids=rule.get('parts',[]);parts=context.parts
    tolerance=positive(rule.get('tolerance',.001),'tolerance')
    if len(set(ids))!=len(ids):raise ValueError('Duplicate rule part references')
    if any(pid not in parts for pid in ids):raise ValueError('Missing parts: '+', '.join(pid for pid in ids if pid not in parts))
    severity=rule.get('severity','FAIL')
    if severity not in ('FAIL','WARNING'):raise ValueError('severity must be FAIL or WARNING')
    if severity=='WARNING' and not str(rule.get('reason','')).strip():raise ValueError('Warning-only rules require a reason')
    def result(ok,message,affected=None,**kw):
        return dict(status='PASS' if ok else severity,rule=kind,parts=ids if affected is None else affected,message=message+(' '+rule['reason'] if not ok and severity=='WARNING' else ''),**kw)
    if kind=='stock_fit':
        findings=[];unspecified={}
        for pid in ids:
            p=parts[pid];stock=context.model['stocks'][p['stock']];blank=p.get('blank_size',p['size'])
            if any(not math.isfinite(v) or v<=0 for v in blank):raise ValueError(f'{pid}: invalid stock blank')
            if stock.get('section'):
                length=p.get('cut_length');positive(length,'cut_length')
                actual=sorted(blank);section=sorted(stock['section'])
                fits_section=any(all(abs(a-b)<=tolerance for a,b in zip(sorted(blank[j] for j in range(3) if j!=i),section)) and abs(blank[i]-length)<=tolerance for i in range(3))
                ok=fits_section and length<=max(stock['lengths'])+tolerance
                findings.append(result(ok,f'{pid}: blank {blank}; cut {length:g} in; longest stock {max(stock["lengths"]):g} in.',[pid],measured={'cut_length_in':length,'max_stock_length_in':max(stock['lengths'])}))
            elif stock.get('sheet'):
                dims=sorted(blank)[-2:];sheet=sorted(stock['sheet'])
                ok=all(a<=b+tolerance for a,b in zip(dims,sheet))
                findings.append(result(ok,f'{pid}: blank {dims[0]:g} × {dims[1]:g} in; sheet {sheet[0]:g} × {sheet[1]:g} in. Nesting and grain direction not checked.',[pid],measured={'blank_in':dims,'sheet_in':sheet}))
            else:unspecified.setdefault(p['stock'],[]).append(pid)
        for stock,stock_ids in unspecified.items():
            findings.append(dict(status='UNVERIFIED',rule=kind,parts=stock_ids,message=f'{stock}: no purchasable stock dimensions specified for {len(stock_ids)} parts.'))
        return findings
    if kind=='solid_collision':
        exceptions={}
        for exception in rule.get('exceptions',[]):
            pair=exception.get('parts',[]);reason=exception.get('reason','')
            if len(pair)!=2 or len(set(pair))!=2 or any(p not in ids for p in pair) or not isinstance(reason,str) or not reason.strip():raise ValueError('Collision exceptions need two selected parts and a nonempty reason')
            exceptions[frozenset(pair)]=reason
        findings=[];checked=[]
        for pid in ids:
            try:context.bounds(pid);checked.append(pid)
            except (ValueError,KeyError,TypeError) as error:findings.append(dict(status='UNVERIFIED',rule=kind,parts=[pid],message=f'Unsupported or invalid solid: {error}'))
        ordered=sorted(checked,key=lambda pid:context.bounds(pid)[0][0]);candidates=0
        for i,a in enumerate(ordered):
            ba=context.bounds(a)
            for b in ordered[i+1:]:
                bb=context.bounds(b)
                if bb[0][0]>=ba[0][1]-tolerance:break
                if any(min(x[1],y[1])-max(x[0],y[0])<=tolerance for x,y in zip(ba,bb)):continue
                candidates+=1;hit=geo.collision(context.solid(a),context.solid(b),tolerance)
                if hit:
                    reason=exceptions.get(frozenset((a,b)))
                    finding=result(False,f'{a} intersects {b}: separating translation {hit["penetration_in"]:.4g} in.'+(' Allowed: '+reason if reason else ''),[a,b],measured={'penetration_in':hit['penetration_in']},location=hit['location'])
                    if reason:finding['status']='WARNING';finding['exception']=reason
                    findings.append(finding)
        failed={pid for f in findings for pid in f['parts']}
        passed=[pid for pid in checked if pid not in failed]
        if passed:findings.append(result(True,f'{len(passed)} parts have no internal solid collisions in this scope; {candidates} candidate pairs tested.',passed))
        return findings
    if kind=='minimum_contact':
        if len(ids)!=2:raise ValueError('minimum_contact requires two parts')
        required=positive(rule['minimum_area'],'minimum_area')
        direction=rule.get('normal')
        if direction is not None and (len(direction)!=3 or not all(math.isfinite(v) for v in direction) or geo.norm(direction)<geo.EPS):raise ValueError('normal must be a nonzero finite vector')
        a,b=map(context.solid,ids);area,location=geo.contact_area(a,b,tolerance,direction)
        return [result(area+geo.EPS>=required,f'Contact area {area:.4g} sq in; required {required:g} sq in.',measured={'contact_area_sq_in':area,'minimum_area_sq_in':required},location=location)]
    if kind=='face_alignment':
        if len(ids)!=2:raise ValueError('face_alignment requires two parts')
        axis=rule['axis'];faces=rule.get('faces',['min','min']);offset=rule.get('offset',0)
        if axis not in (0,1,2) or isinstance(axis,bool) or len(faces)!=2 or any(f not in ('min','max') for f in faces) or not math.isfinite(offset):raise ValueError('Invalid axis, faces or offset')
        values=[context.bounds(pid)[axis][0 if face=='min' else 1] for pid,face in zip(ids,faces)]
        measured=values[1]-values[0];error=measured-offset
        return [result(abs(error)<=tolerance,f'{"XYZ"[axis]} face offset {measured:.4g} in; expected {offset:g} in; discrepancy {error:.4g} in.',measured={'offset_in':measured,'expected_offset_in':offset,'error_in':error},location=geo.mean([geo.mean([v for s in context.solid(pid) for f in s for v in f]) for pid in ids]))]
    if kind=='opening_clearance':
        opening=rule['opening'];clearance=positive(rule.get('clearance',0),'clearance',True)
        if len(opening['size'])!=3 or any(v<=0 or not math.isfinite(v) for v in opening['size']):raise ValueError('Invalid opening volume')
        # Expansion in opening-local axes. Omit units such as the door leaf from scope.
        opening={**opening,'size':[v+2*clearance for v in opening['size']],'origin':[v-clearance for v in opening['origin']]}
        void=geo.solids(opening);findings=[];hit_ids=set()
        for pid in ids:
            hit=geo.collision(void,context.solid(pid),tolerance)
            if hit:
                hit_ids.add(pid);findings.append(result(False,f'{pid} intrudes into the clear opening by {hit["penetration_in"]:.4g} in.',[pid],measured={'penetration_in':hit['penetration_in'],'clearance_in':clearance},location=hit['location']))
        clear=[pid for pid in ids if pid not in hit_ids]
        if clear:findings.append(result(True,'Selected parts clear the declared opening volume.',clear))
        return findings
    if kind=='panel_support':
        if len(ids)<2:raise ValueError('panel_support requires a panel and supports')
        panel=parts[ids[0]]
        if panel.get('profile') or panel.get('seats'):return [dict(status='UNVERIFIED',rule=kind,parts=ids,message='Panel support currently requires an uncut rectangular panel; arbitrary rotations are supported.')]
        thin=rule.get('thickness_axis',min(range(3),key=lambda i:panel['size'][i]))
        if thin not in (0,1,2):raise ValueError('Invalid thickness_axis')
        axes=[i for i in range(3) if i!=thin];outward=[0,0,0];outward[thin]=-1
        n=geo.rotate(outward,panel.get('rotation',[0,0,0]));basis=[]
        for axis in axes:
            v=[0,0,0];v[axis]=1;basis.append(geo.rotate(v,panel.get('rotation',[0,0,0])))
        center=geo.add(panel['origin'],geo.mul(panel['size'],.5));point=geo.add(center,geo.mul(n,panel['size'][thin]/2))
        footprints=[]
        for pid in ids[1:]:
            if geo.collision(context.solid(ids[0]),context.solid(pid),tolerance):return [result(False,f'{pid} penetrates the panel instead of supporting its underside.',[ids[0],pid])]
            for solid in context.solid(pid):
                for face in solid:
                    if geo.dot(geo.normal(face),n)>-1+1e-7 or any(abs(geo.dot(n,geo.sub(v,point)))>tolerance for v in face):continue
                    footprints.append([(geo.dot(geo.sub(v,center),basis[0]),geo.dot(geo.sub(v,center),basis[1])) for v in face])
        dimensions=[panel['size'][i] for i in axes];required=positive(rule['bearing_width'],'bearing_width');findings=[]
        for axis in (0,1):
            for end in (0,1):
                key=f'{axis}:{end}';width=positive(rule.get('edge_widths',{}).get(key,required),'edge bearing width')
                if width>dimensions[axis]:raise ValueError('Bearing width exceeds panel size')
                lo=[-d/2 for d in dimensions];hi=[d/2 for d in dimensions]
                if end==0:hi[axis]=lo[axis]+width
                else:lo[axis]=hi[axis]-width
                band=[(lo[0],lo[1]),(hi[0],lo[1]),(hi[0],hi[1]),(lo[0],hi[1])]
                clipped=[geo.intersect2d(poly,band) for poly in footprints];area=polygon_union_area([p for p in clipped if len(p)>2]);expected=width*dimensions[1-axis]
                gap=max(0,expected-area)
                location=geo.add(point,geo.add(geo.mul(basis[0],(lo[0]+hi[0])/2),geo.mul(basis[1],(lo[1]+hi[1])/2)))
                findings.append(result(gap<=max(geo.EPS,tolerance*dimensions[1-axis]),f'Panel edge {key}: {area:.4g}/{expected:.4g} sq in supported; missing {gap:.4g} sq in.',measured={'edge':key,'supported_area_sq_in':area,'required_area_sq_in':expected,'missing_area_sq_in':gap},location=location))
        return findings
    raise ValueError('Unknown measured rule')


def coverage(model,findings):
    """Coverage means a rule ran, never structural approval. Keep categories separate."""
    categories={'solid_collision':'collisions','stock_fit':'stock','minimum_contact':'support','panel_support':'support','bearing':'support','panel_edge_bearing':'support','rafter_seats':'support','plate_end_bearing':'support','face_alignment':'alignment','seat_alignment':'alignment','corner_lap':'alignment','level_top':'alignment','opening_clearance':'openings','opening_edge':'openings','non_overlap':'collisions','joist_end_restraint':'support','roof_slope':'alignment','edgewise_header':'alignment'}
    bypart={p['id']:set() for p in model['parts']}
    for f in findings:
        if f['status'] in ('PASS','FAIL','WARNING') and f['rule'] in categories:
            for pid in f['parts']:
                if pid in bypart:bypart[pid].add(categories[f['rule']])
    groups={}
    for p in model['parts']:groups.setdefault(p['assembly'],[]).append(p['id'])
    priority = {'PASS': 0, 'WARNING': 1, 'UNVERIFIED': 2, 'FAIL': 3}
    requirements = []
    declared = model.get('validation', {}).get('requirements', [])
    for requirement in declared if isinstance(declared, list) else []:
        if not isinstance(requirement, dict) or not requirement.get('rule_id'):
            continue
        matching = [f for f in findings if f.get('rule_id') == requirement['rule_id']
                    and f.get('rule_id_explicit')]
        status = max((f['status'] for f in matching), key=priority.get) if matching else 'UNVERIFIED'
        requirements.append({**requirement, 'status': status})
    return {'total_parts':len(bypart),'checked_parts':sum(bool(v) for v in bypart.values()),'unchecked_parts':[p for p,c in bypart.items() if not c],
            'requirements': requirements,
            'assemblies':[{'name':name,'total_parts':len(ids),'checked_parts':sum(bool(bypart[i]) for i in ids),'categories':{cat:sum(cat in bypart[i] for i in ids) for cat in sorted(set(categories.values()))}} for name,ids in groups.items()]}
