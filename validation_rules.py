"""Measured geometric validation. No structural thresholds are inferred."""
import math
from itertools import combinations
import solid_geometry as geo

KINDS={'minimum_section','solid_collision','minimum_contact','face_alignment','opening_clearance','panel_support','stock_fit','assembly_presence','plate_splice_offset','panel_joint','surface_gap','minimum_total_contact','profile_section','within_envelope','motion_clearance','blocking_spacing','host_depth'}


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
    if kind=='minimum_section':
        if len(ids)!=1: raise ValueError('minimum_section requires one rectangular member')
        part=parts[ids[0]]
        if any(part.get(key) for key in ('outline','profile','seats')):
            return [dict(status='UNVERIFIED',rule=kind,parts=ids,message='Section check requires an uncut rectangular member.')]
        thickness_axis=rule['thickness_axis'];depth_axis=rule['depth_axis']
        if type(thickness_axis) is not int or type(depth_axis) is not int or thickness_axis not in (0,1,2) or depth_axis not in (0,1,2) or thickness_axis==depth_axis:
            raise ValueError('Section axes must be distinct local axes')
        thickness=positive(rule['minimum_thickness'],'minimum_thickness')
        depth=positive(rule['minimum_depth'],'minimum_depth')
        actual_t=part['size'][thickness_axis];actual_h=part['size'][depth_axis]
        aligned=True
        if 'depth_direction' in rule:
            direction=rule['depth_direction']
            if len(direction)!=3 or not all(math.isfinite(v) for v in direction) or geo.norm(direction)<geo.EPS:
                raise ValueError('depth_direction must be a finite nonzero world vector')
            local=[1 if i==depth_axis else 0 for i in range(3)]
            world=geo.rotate(local,part.get('rotation',[0,0,0]))
            aligned=abs(geo.dot(world,geo.unit(direction)))>=1-1e-7
        return [result(aligned and actual_t+tolerance>=thickness and actual_h+tolerance>=depth,
                       f'Actual section {actual_t:g} x {actual_h:g} in; required at least {thickness:g} x {depth:g} in.'+(' Depth axis is not aligned with the declared world direction.' if not aligned else ''))]
    if kind=='host_depth':
        normal=rule['direction'];origin=rule['origin'];depth=positive(rule['depth'],'depth')
        if len(normal)!=3 or geo.norm(normal)<geo.EPS or len(origin)!=3 or not all(math.isfinite(v) for v in [*normal,*origin]):
            raise ValueError('Invalid host depth interface')
        normal=geo.unit(normal)
        extents=[geo.dot(geo.sub(v,origin),normal) for pid in ids for s in context.solid(pid) for v in geo.vertices(s)]
        lo,hi=min(extents),max(extents)
        return [result(lo<=tolerance and hi>=depth-tolerance, f'Product depth interval [{lo:g}, {hi:g}] must span host [0, {depth:g}] in.')]
    if kind=='blocking_spacing':
        direction=rule['direction']
        if len(direction)!=3 or not all(math.isfinite(v) for v in direction) or geo.norm(direction)<geo.EPS:
            raise ValueError('direction must be a finite nonzero vector')
        direction=geo.unit(direction);maximum=positive(rule['maximum_spacing'],'maximum_spacing')
        groups=rule['rows']
        if len(groups)<2 or any(not group for group in groups) or set(sum(groups,[]))!=set(ids):
            raise ValueError('Blocking rows must include both end restraints and all declared blocks')
        centers=[]
        for group in groups:
            values=[geo.dot(geo.add(parts[pid]['origin'],geo.mul(parts[pid]['size'],.5)),direction) for pid in group]
            if max(values)-min(values)>tolerance:return [result(False,'Members in a blocking row are not aligned.')]
            centers.append(sum(values)/len(values))
        gaps=[b-a for a,b in zip(centers,centers[1:])]
        ok=all(gap>tolerance and gap<=maximum+tolerance for gap in gaps)
        return [result(ok, f'Largest restraint-row interval {max(gaps):g} in; allowed {maximum:g} in.',measured={'maximum_gap_in':max(gaps),'allowed_gap_in':maximum})]
    if kind=='within_envelope':
        envelope=rule['envelope'];geo.solids(envelope)
        center=geo.add(envelope['origin'],geo.mul(envelope['size'],.5))
        basis=[geo.rotate(tuple(1 if i==j else 0 for i in range(3)),envelope.get('rotation',[0,0,0])) for j in range(3)]
        findings=[]
        for pid in ids:
            outside=max(abs(geo.dot(geo.sub(v,center),basis[i]))-envelope['size'][i]/2 for s in context.solid(pid) for v in geo.vertices(s) for i in range(3))
            findings.append(result(outside<=tolerance, f'{pid}: '+('fits the declared installation envelope.' if outside<=tolerance else f'exceeds installation envelope by {outside:g} in.'),[pid]))
        return findings
    if kind=='motion_clearance':
        moving=rule['moving_parts']
        if not isinstance(moving,list) or not moving or len(set(moving))!=len(moving) or any(pid not in ids for pid in moving):
            raise ValueError('Moving parts must be a nonempty subset of the rule scope')
        motion=rule['motion'];moved={}
        if motion.get('kind')=='rotate_z':
            pivot=motion['pivot'];angle=motion['angle']
            if len(pivot)!=3 or any(not math.isfinite(v) for v in pivot) or not math.isfinite(angle):raise ValueError('Invalid rotation state')
            for pid in moving:
                p=parts[pid]
                if any(abs(v)>tolerance for v in p.get('rotation',[0,0,0])[:2]):raise ValueError('Vertical-hinge state requires upright moving parts')
                center=geo.add(p['origin'],geo.mul(p['size'],.5))
                center=geo.add(pivot,geo.rotate(geo.sub(center,pivot),(0,0,angle)))
                posed={**p,'origin':geo.sub(center,geo.mul(p['size'],.5)),'rotation':[0,0,p.get('rotation',[0,0,0])[2]+angle]}
                moved[pid]=geo.solids(posed)
        elif motion.get('kind')=='translate':
            offset=motion['offset']
            if len(offset)!=3 or any(not math.isfinite(v) for v in offset):raise ValueError('Invalid translation state')
            for pid in moving:moved[pid]=geo.solids({**parts[pid],'origin':geo.add(parts[pid]['origin'],offset)})
        else:raise ValueError('Unknown motion kind')
        static=[pid for pid in ids if pid not in moving];findings=[]
        for pid,solids in moved.items():
            for obstacle in static:
                hit=geo.collision(solids,context.solid(obstacle),tolerance)
                if hit:findings.append(result(False,f'{pid} collides with {obstacle} in the declared operating state.',[pid,obstacle],location=hit['location']))
        if not findings:findings.append(result(True,'Declared operating state clears the selected obstacles; this is not a continuous swept-volume proof.'))
        return findings
    if kind=='minimum_total_contact':
        if len(ids)<2: raise ValueError('minimum_total_contact needs a member and supports')
        required=positive(rule['minimum_area'],'minimum_area')
        normal=rule.get('normal',[0,0,-1])
        if len(normal)!=3 or not all(math.isfinite(v) for v in normal) or geo.norm(normal)<geo.EPS:
            raise ValueError('normal must be a finite nonzero vector')
        n=geo.unit(normal)
        trial=(1,0,0) if abs(n[0])<.9 else (0,1,0)
        u=geo.unit(geo.cross(n,trial));v=geo.cross(n,u)
        groups=[]
        for solid in context.solid(ids[0]):
            for face in solid:
                if geo.dot(geo.normal(face),n)<1-1e-7: continue
                level=geo.dot(n,face[0]);project=lambda p:(geo.dot(p,u),geo.dot(p,v))
                group=next((g for g in groups if abs(g[0]-level)<=tolerance),None)
                if group is None: group=[level,[]];groups.append(group)
                for pid in ids[1:]:
                    for support in context.solid(pid):
                        for other in support:
                            if geo.dot(geo.normal(other),n)>-1+1e-7 or any(abs(geo.dot(n,p)-level)>tolerance for p in other):continue
                            poly=geo.intersect2d([project(p) for p in face],[project(p) for p in other])
                            if len(poly)>2: group[1].append(poly)
        area=sum(polygon_union_area(polys) for _,polys in groups)
        return [result(area+geo.EPS>=required, f'Union contact area {area:g} sq in; required {required:g} sq in.',
                       measured={'contact_area_sq_in':area,'minimum_area_sq_in':required})]
    if kind=='profile_section':
        if len(ids)!=1: raise ValueError('profile_section needs one cut member')
        p=parts[ids[0]]
        if not p.get('outline'): return [result(False,'Required cut member profile is missing.')]
        # Confirm the actual outline is valid before measuring remaining material.
        context.solid(ids[0])
        lo,hi=rule['interval'];positive(hi-lo,'section interval')
        if lo<0 or hi>p['size'][1]: raise ValueError('Section interval exceeds blank')
        maximum=positive(rule['maximum_notch'],'maximum_notch',True)
        minimum=positive(rule['minimum_remaining'],'minimum_remaining')
        if not isinstance(rule.get('basis'),str) or not rule['basis'].strip(): raise ValueError('Section limits need a source/design basis')
        points=p['outline'];xs=sorted(set([lo,hi]+[x for x,z in points if lo<x<hi]))
        samples=[a+(b-a)*f for a,b in zip(xs,xs[1:]) for f in (1e-6,.5,1-1e-6)]
        remaining=[];notches=[]
        for x in samples:
            zs=[]
            for (a,b),(c,d) in zip(points,points[1:]+points[:1]):
                if min(a,c)<x<max(a,c): zs.append(b+(d-b)*(x-a)/(c-a))
            if len(zs)!=2: return [result(False,'Cut profile is not a single continuous section through the seat.')]
            low,high=sorted(zs)
            if 'plumb_top_start' in rule:
                start=positive(rule['plumb_top_start'],'plumb_top_start')
                expected=p['size'][2]*min(1,x/start)
                if abs(high-expected)>tolerance:
                    return [result(False,'Upper rafter profile differs from the declared stock plane/plumb end.')]
                # Notch depth is normal to the stock plane. A plumb tail clips
                # the end wedge; it must not count as additional seat notching.
                remaining.append(p['size'][2]-low)
            else: remaining.append(high-low)
            notches.append(low)
        cut=max(notches);depth=min(remaining)
        return [result(cut<=maximum+tolerance and depth+tolerance>=minimum,
                       f'Maximum notch {cut:g} in; minimum remaining normal section {depth:g} in. Limits from: '+rule['basis'],
                       measured={'notch_depth_in':cut,'remaining_section_in':depth})]
    if kind=='assembly_presence':
        return [result(True, f'All {len(ids)} declared assembly parts are present.')]
    if kind=='surface_gap':
        if len(ids)!=2: raise ValueError('surface_gap requires two parts')
        direction=rule['direction']
        if len(direction)!=3 or not all(math.isfinite(v) for v in direction) or geo.norm(direction)<geo.EPS:
            raise ValueError('direction must be a finite nonzero vector')
        direction=geo.unit(direction);expected=rule.get('gap',0)
        positive(expected,'gap',True)
        values=[(min(geo.dot(v,direction) for s in context.solid(pid) for v in geo.vertices(s)),
                 max(geo.dot(v,direction) for s in context.solid(pid) for v in geo.vertices(s))) for pid in ids]
        gap=values[1][0]-values[0][1]
        return [result(abs(gap-expected)<=tolerance, f'Surface gap {gap:g} in; specified {expected:g} in.',
                       measured={'gap_in':gap,'expected_gap_in':expected})]
    if kind=='plate_splice_offset':
        direction=rule['direction']
        if len(direction)!=3 or not all(math.isfinite(v) for v in direction) or geo.norm(direction)<geo.EPS:
            raise ValueError('direction must be a finite nonzero vector')
        direction=geo.unit(direction)
        layers=rule['layers']
        if len(layers)!=2 or any(not layer for layer in layers) or set(sum(layers,[]))!=set(ids):
            raise ValueError('Two complete plate layers are required')
        required=positive(rule['minimum_offset'],'minimum_offset')
        joints=[]
        for layer in layers:
            spans=sorted((min(geo.dot(v,direction) for solid in context.solid(pid) for v in geo.vertices(solid)),
                          max(geo.dot(v,direction) for solid in context.solid(pid) for v in geo.vertices(solid))) for pid in layer)
            if any(abs(a[1]-b[0])>tolerance for a,b in zip(spans,spans[1:])):
                return [result(False, 'Plate layer contains a gap or overlapping splice.')]
            joints.append([span[1] for span in spans[:-1]])
        offsets=[abs(a-b) for a in joints[0] for b in joints[1]]
        minimum=min(offsets) if offsets else None
        return [result(minimum is None or minimum+tolerance>=required,
                       'No opposed in-line splices.' if minimum is None else f'Closest plate splices {minimum:g} in apart; required {required:g} in.',
                       measured={'minimum_offset_in':minimum,'required_offset_in':required})]
    if kind=='panel_joint':
        if len(ids)!=2 or not isinstance(rule.get('basis'),str) or not rule['basis'].strip():
            raise ValueError('panel_joint needs two panels and a product/detail basis')
        a,b=(parts[pid] for pid in ids)
        if any(p.get('profile') or p.get('seats') or p.get('outline') for p in (a,b)):
            return [dict(status='UNVERIFIED',rule=kind,parts=ids,message='Joint check requires rectangular panels.')]
        axis=rule.get('thickness_axis',2)
        if axis not in (0,1,2): raise ValueError('Invalid thickness axis')
        normal=[0,0,0];normal[axis]=1
        na=geo.rotate(normal,a.get('rotation',[0,0,0]));nb=geo.rotate(normal,b.get('rotation',[0,0,0]))
        ca=geo.add(a['origin'],geo.mul(a['size'],.5));cb=geo.add(b['origin'],geo.mul(b['size'],.5))
        coplanar=geo.dot(na,nb)>1-1e-7 and abs(geo.dot(na,geo.sub(cb,ca)))<=tolerance and abs(a['size'][axis]-b['size'][axis])<=tolerance
        area,_=geo.contact_area(context.solid(ids[0]),context.solid(ids[1]),tolerance)
        required=positive(rule['minimum_area'],'minimum_area')
        ok=coplanar and area+geo.EPS>=required and not geo.collision(context.solid(ids[0]),context.solid(ids[1]),tolerance)
        return [result(ok, 'Panel joint adjacency and coplanarity checked; tongue geometry/capacity follows the specified product detail: '+rule['basis'],
                       measured={'contact_area_sq_in':area,'minimum_area_sq_in':required})]
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
                thickness=stock.get('sheet_thickness')
                thickness_note=''
                if thickness is not None:
                    from stud.model import sheet_blank_candidates
                    positive(thickness,'sheet_thickness')
                    candidates=sheet_blank_candidates(blank,thickness,tolerance)
                    matches=[candidate for candidate in candidates if all(a<=b+tolerance for a,b in zip(candidate,sheet))]
                    ok=bool(matches)
                    if matches: dims=matches[0]
                    thickness_note=f' Stock requires {thickness:g} in thickness.'
                findings.append(result(ok,f'{pid}: blank {dims[0]:g} × {dims[1]:g} in; sheet {sheet[0]:g} × {sheet[1]:g} in.{thickness_note} Nesting and grain direction not checked.',[pid],measured={'blank_in':dims,'sheet_in':sheet,'sheet_thickness_in':thickness}))
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
        faces=rule.get('faces',['min','min']);offset=rule.get('offset',0)
        if len(faces)!=2 or any(f not in ('min','max') for f in faces) or not math.isfinite(offset):raise ValueError('Invalid faces or offset')
        if 'direction' in rule:
            direction=rule['direction']
            if 'axis' in rule or not isinstance(direction,(list,tuple)) or len(direction)!=3 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in direction) or geo.norm(direction)<geo.EPS:
                raise ValueError('Use a nonzero finite direction or a world axis, exclusively')
            direction=geo.unit(direction)
            values=[(min if face=='min' else max)(geo.dot(v,direction) for solid in context.solid(pid) for f in solid for v in f) for pid,face in zip(ids,faces)]
            label='Projected'
        else:
            axis=rule['axis']
            if axis not in (0,1,2) or isinstance(axis,bool):raise ValueError('Invalid axis')
            values=[context.bounds(pid)[axis][0 if face=='min' else 1] for pid,face in zip(ids,faces)]
            label='XYZ'[axis]
        measured=values[1]-values[0];error=measured-offset
        return [result(abs(error)<=tolerance,f'{label} face offset {measured:.4g} in; expected {offset:g} in; discrepancy {error:.4g} in.',measured={'offset_in':measured,'expected_offset_in':offset,'error_in':error},location=geo.mean([geo.mean([v for s in context.solid(pid) for f in s for v in f]) for pid in ids]))]
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
        if panel.get('profile') or panel.get('seats'):return [dict(status='UNVERIFIED',rule=kind,parts=ids,message='Panel support requires a constant-thickness rectangular or outline panel.')]
        thin=rule.get('thickness_axis',min(range(3),key=lambda i:panel['size'][i]))
        if thin not in (0,1,2):raise ValueError('Invalid thickness_axis')
        if panel.get('outline') and thin!=0:raise ValueError('Outline panel thickness axis must be its extrusion axis 0')
        axes=[i for i in range(3) if i!=thin];outward=[0,0,0]
        face=rule.get('support_face','min')
        if face not in ('min','max'): raise ValueError('Invalid support_face')
        outward[thin]=-1 if face=='min' else 1
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
        if panel.get('outline'):
            from profile_geometry import triangulate_outline
            if 'edges' in rule or 'edge_widths' in rule:raise ValueError('Outline panel uses its complete polygon perimeter')
            ring=[(y-dimensions[0]/2,z-dimensions[1]/2) for y,z in panel['outline']]
            if sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(ring,ring[1:]+ring[:1]))<0:ring.reverse()
            triangles=triangulate_outline(ring)
            for i,(a,b) in enumerate(zip(ring,ring[1:]+ring[:1])):
                length=math.dist(a,b);inward=(-(b[1]-a[1])*required/length,(b[0]-a[0])*required/length)
                band=[a,b,(b[0]+inward[0],b[1]+inward[1]),(a[0]+inward[0],a[1]+inward[1])]
                regions=[geo.intersect2d(triangle,band) for triangle in triangles]
                regions=[region for region in regions if geo.polygon_area(region)>geo.EPS]
                expected=polygon_union_area(regions)
                clipped=[geo.intersect2d(poly,region) for poly in footprints for region in regions]
                area=polygon_union_area([poly for poly in clipped if geo.polygon_area(poly)>geo.EPS])
                gap=max(0,expected-area)
                findings.append(result(gap<=tolerance*max(1,length),
                    f'Outline edge {i}: unsupported bearing area {gap:g} sq in; band {required:g} in.',
                    measured={'edge':i,'unsupported_area_sq_in':gap,'bearing_width_in':required}))
            return findings
        edges=rule.get('edges',['0:0','0:1','1:0','1:1'])
        if not isinstance(edges,list) or not edges or len(edges)!=len(set(edges)) or any(e not in ('0:0','0:1','1:0','1:1') for e in edges):
            raise ValueError('edges must select distinct panel edges')
        for axis in (0,1):
            for end in (0,1):
                key=f'{axis}:{end}'
                if key not in edges: continue
                width=positive(rule.get('edge_widths',{}).get(key,required),'edge bearing width')
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
    categories={'minimum_section':'stock','host_depth':'openings','blocking_spacing':'support','within_envelope':'openings','motion_clearance':'openings','minimum_total_contact':'support','profile_section':'support','assembly_presence':'inventory','surface_gap':'alignment','plate_splice_offset':'alignment','panel_joint':'support','solid_collision':'collisions','stock_fit':'stock','minimum_contact':'support','panel_support':'support','bearing':'support','panel_edge_bearing':'support','rafter_seats':'support','plate_end_bearing':'support','face_alignment':'alignment','seat_alignment':'alignment','corner_lap':'alignment','level_top':'alignment','opening_clearance':'openings','opening_edge':'openings','non_overlap':'collisions','joist_end_restraint':'support','roof_slope':'alignment','edgewise_header':'alignment'}
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
