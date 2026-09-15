"""Stock framing and explicitly incomplete truss coordination representations."""
from dataclasses import dataclass
import math

import cadquery as cq

from .roof_layout import (RoofFace, layout_roofs, roof_stations, boundary_planes,
                          clip_polygon, EPS, _area)
from .stock import Plane, cut_member, StockParts
from .solids import round_member


@dataclass(frozen=True)
class RafterField:
    face: str
    profile: object
    spacing: float
    origin: tuple = (0,0)
    direction: tuple | None = None
    edge_setback: float = 0
    station_bounds: tuple | None = None

    def __post_init__(self):
        from .framing import MemberProfile
        if self.station_bounds is not None:
            bounds=tuple(self.station_bounds)
            if len(bounds)!=2 or not all(math.isfinite(v) for v in bounds) or bounds[0]>=bounds[1]:raise ValueError('Station bounds need an increasing pair of finite perpendicular coordinates.')
            object.__setattr__(self,'station_bounds',bounds)
        object.__setattr__(self,'origin',tuple(self.origin))
        if self.direction is not None:object.__setattr__(self,'direction',tuple(self.direction))
        for pair in (self.origin, *((self.direction,) if self.direction is not None else ())):
            if len(pair)!=2 or not all(math.isfinite(v) for v in pair):raise ValueError('Roof directions and origins need finite XY pairs.')
        if not self.face or not isinstance(self.profile,MemberProfile) or self.profile.flange:
            raise ValueError('A rafter field needs a face and rectangular stock profile.')
        if not math.isfinite(self.spacing) or self.spacing<=self.profile.width or not math.isfinite(self.edge_setback) or self.edge_setback<0:
            raise ValueError('Rafter spacing must exceed its width; setback cannot be negative.')


@dataclass(frozen=True)
class RoofMember:
    id: str
    face: str
    start: tuple
    end: tuple
    profile: object
    cuts: tuple

    def cut(self):
        """Preserve original stock while clipping compound ends and backing."""
        dx,dy=self.end[0]-self.start[0],self.end[1]-self.start[1]
        start=[];end=[]
        for plane in self.cuts:
            if abs(plane.normal[2])>EPS:continue
            along=plane.normal[0]*dx+plane.normal[1]*dy
            if along<-EPS:start.append(plane)
            elif along>EPS:end.append(plane)
        # Select the active end boundary; all the domain planes also trim the
        # stock corners. These are finite face cuts, not supporting-member Booleans.
        sp=min(start,key=lambda p:abs(p.signed_distance(self.start)))
        ep=min(end,key=lambda p:abs(p.signed_distance(self.end)))
        return cut_member(self.start,self.end,(self.profile.width,self.profile.depth),
                          start_plane=sp,end_plane=ep,top_planes=self.cuts)


def plan_roof_members(layout, fields):
    """Plan visible face framing without Model mutation or automatic sizing.

    Setbacks are measured in plan from every patch boundary. For structural
    hips/valleys use their actual finite faces as additional project cut planes.
    Artificial patch boundaries may split stock; inspect their support details.
    """
    fields=tuple(fields)
    if len({f.face for f in fields})!=len(fields):raise ValueError('One field per named roof face.')
    known={f.id for f in layout.faces}
    if any(f.face not in known for f in fields):raise ValueError('Unknown roof field face.')
    result=[]
    for field in fields:
        for patch_index,face in enumerate(f for f in layout.patches if f.id==field.face):
            poly=face.outline
            for n,d in boundary_planes(face.outline):poly=clip_polygon(poly,n,d-field.edge_setback)
            if not poly:continue
            normal=face.plane.normal
            direction=field.direction or (-normal[0],-normal[1])
            if math.hypot(*direction)<EPS:raise ValueError('A level roof field needs a member direction.')
            local=layout_roofs((RoofFace(face.id,face.plane,poly),))
            cuts=tuple(Plane((n[0]*d,n[1]*d,0),(*n,0)) for n,d in boundary_planes(poly))+(face.plane,)
            for station,segments in roof_stations(local,direction=direction,spacing=field.spacing,origin=field.origin):
                for i,segment in enumerate(segments):
                    if field.station_bounds is not None:
                        d=math.hypot(*direction);v=(-direction[1]/d,direction[0]/d)
                        coordinate=sum(a*b for a,b in zip(v,segment.start))
                        if not field.station_bounds[0]-EPS<=coordinate<=field.station_bounds[1]+EPS:continue
                    if math.dist(segment.start,segment.end)<=field.profile.width:continue
                    result.append(RoofMember(f'{field.face}.p{patch_index}.station{station}.s{i}',field.face,
                                             segment.start,segment.end,field.profile,cuts))
    return tuple(result)


def cut_bearing_seats(result, supports):
    """Cut vertical seat pockets from named horizontal faces of world solids.

    Return (stock_result, touched_support_ids). Notch sizing is caller-owned;
    the cut must leave one valid solid. Works for common, hip and valley stock.
    """
    shape,location,source_blank=result
    blank={**source_blank,'operations':list(source_blank.get('operations',()))}
    world=shape.moved(location);seats=[]
    for pid,support in supports.items():
        a=world.BoundingBox();b=support.BoundingBox()
        if not (min(a.xmax,b.xmax)>max(a.xmin,b.xmin)+EPS and min(a.ymax,b.ymax)>max(a.ymin,b.ymin)+EPS and b.zmax>a.zmin):continue
        for face in support.Faces():
            if face.geomType()!='PLANE' or face.normalAt().z<1-EPS:continue
            a=world.BoundingBox();b=face.BoundingBox()
            if not (min(a.xmax,b.xmax)>max(a.xmin,b.xmin)+EPS and min(a.ymax,b.ymax)>max(a.ymin,b.ymin)+EPS and a.zmin<b.zmax<a.zmax):continue
            cutter=cq.Solid.extrudeLinear(face.outerWire(),face.innerWires(),cq.Vector(0,0,-(b.zmax-a.zmin+1)))
            if world.intersect(cutter).Volume()>EPS:
                world=world.cut(cutter).clean();seats.append(pid)
                blank['operations'].append(dict(kind='bearing_seat',frame='world',support=pid,
                    top=b.zmax,outline=[v.Center().toTuple() for v in face.Vertices()]))
    if not world.isValid() or len(world.Solids())!=1:raise ValueError('Bearing cuts sever the member.')
    return (world.moved(location.inverse),location,blank),tuple(sorted(set(seats)))


def frame_roof(model, layout, fields, *, object_id='roof', parent=None, bearings=(), bearing_length=None):
    """Register sawn framing with stock checks and unresolved end connections.

    Named horizontal bearing faces cut vertical seat pockets, with their
    original stock and support checks retained. This does not size notches or
    add ridge/hip/valley supports, ties or hardware. The
    returned plan gives callers stable members for composing those operations.
    """
    plan=plan_roof_members(layout,fields)
    if any(p not in model.shapes for p in bearings):raise ValueError('Unknown roof bearing part.')
    if bearings and (bearing_length is None or not math.isfinite(bearing_length) or bearing_length<=0):
        raise ValueError('Select a positive required bearing length when supplying roof seats.')
    supports={pid:model.shapes[pid]['world'] for pid in bearings}
    model.assembly(object_id,'Roof rafters',parent=parent)
    parts=[];requirements=[]
    profiles={}
    for member in plan:profiles.setdefault(member.profile,[]).append(member)
    for index,(profile,members) in enumerate(profiles.items()):
        stock=StockParts(model,parent=object_id,demand_prefix=object_id+f'.purchase{index}.')
        with model.batch():
            for member in members:
                pid=object_id+'.'+member.id
                cut,seats=cut_bearing_seats(member.cut(),supports)
                stock.add(pid,cut,section=(profile.width,profile.depth),product_id=profile.product_id)
                model.requirement(pid+'.valid','solid_valid',[pid]);requirements.extend([pid+'.valid',pid+'.blank']);parts.append(pid)
                if seats:
                    model.requirement(pid+'.seat','support',[pid,*sorted(set(seats))],threshold=profile.width*bearing_length)
                    requirements.append(pid+'.seat')
                    model.connection(pid+'.notch_detail',parts=[pid,*sorted(set(seats))],description='Seat pocket derived from named horizontal bearing faces.',
                        unresolved=['Verify notch depth, remaining section, required bearing length and uplift connection for this member.'])
        for demand in stock.purchase(stock_lengths=profile.stock_lengths):
            model.demands[demand]['unresolved'].extend(profile.unresolved)
    connection=model.connection(object_id+'.end_details',parts=parts,
        description='Roof-domain member cuts; supporting members and end details are caller-owned.',
        geometry_unresolved=True,unresolved=['Resolve bearing seats, finite ridge/hip/valley interfaces, ties, blocking, uplift hardware and reactions.'])
    model.expect(object_id+'.inventory',parts=[object_id+'.'+m.id for m in plan],requirements=requirements,connections=[connection])
    return dict(parts=parts,plan=plan,layout=layout)


def truss_profile_envelope(model, profile, *, object_id, bottom, diagram_diameter,
                           parent=None, unresolved=()):
    """One factory-truss coordination outline, never a lumber/web cut list.

    profile is a continuous, ordered tuple of RoofSegments. Slopes below the
    supplied bottom are clipped. Thin round strokes deliberately distinguish
    the diagram from physical chords. Width is a display choice, not stock.
    """
    profile=tuple(profile)
    if not profile or not all(math.isfinite(v) for v in (bottom,diagram_diameter)) or diagram_diameter<=0:
        raise ValueError('A truss outline needs a profile, bottom and positive diagram diameter.')
    if any(math.dist(a.end,b.start)>EPS for a,b in zip(profile,profile[1:])):
        raise ValueError('Disconnected roof profiles need separate truss definitions.')
    lines=[]
    for seg in profile:
        a,b=seg.start,seg.end
        if max(a[2],b[2])<=bottom+EPS:continue
        if min(a[2],b[2])<bottom:
            t=(bottom-a[2])/(b[2]-a[2]);cross=tuple(x+t*(y-x) for x,y in zip(a,b))
            if a[2]<bottom:a=cross
            else:b=cross
        if lines and math.dist(lines[-1][1],a)>EPS:
            raise ValueError('Bottom clips this profile into separate trusses; split the input.')
        lines.append((a,b))
    if not lines:return None
    a,b=lines[0][0],lines[-1][1];pa=(*a[:2],bottom);pb=(*b[:2],bottom)
    segments=lines+[(a,pa),(pa,pb),(pb,b)]
    shape=cq.Compound.makeCompound([round_member(a,b,diagram_diameter) for a,b in segments if math.dist(a,b)>EPS])
    model.part(object_id,shape,parent=parent,label='Truss coordination outline — shop design required',
        material='factory.truss.unselected',color='#779baa',lineage={'representation':'coordination_outline','diagram_diameter':diagram_diameter})
    gaps=['Manufacturer truss profile, spacing, chord/web sections, plates, bearings, reactions and permanent bracing require project shop drawings.',*unresolved]
    model.demand(object_id+'.factory',product_id='factory.truss.unselected',specification={'status':'coordination only','bottom':bottom,
        'profile':[[list(s.start),list(s.end)] for s in profile]},object_ids=[object_id],quantity=1,unit='truss',purchase_unit='truss',unresolved=gaps)
    model.requirement(object_id+'.valid','solid_valid',[object_id])
    model.connection(object_id+'.shop_design',parts=[object_id],description='Diagram strokes are not physical chords or webs.',geometry_unresolved=True,unresolved=gaps)
    return object_id


def roof_wall_limit(layout, line, *, depth, clearance):
    """Conservative level wall cap under all roof planes across its full width.

    clearance is vertical. line is the wall centerline. Missing roof coverage
    raises instead of silently supplying an arbitrary height. Use section() for
    sloping infill above the resulting level cap.
    """
    if not all(math.isfinite(v) and v>=0 for v in (depth,clearance)) or depth<=0:
        raise ValueError('Wall depth must be positive and clearance nonnegative.')
    left,right=line.offset(depth/2),line.offset(-depth/2)
    footprint=(right.start,right.end,left.end,left.start)
    limits=[];covered=0
    for patch in layout.patches:
        poly=patch.outline
        for n,d in boundary_planes(footprint):poly=clip_polygon(poly,n,d)
        if not poly:continue
        covered+=_area(poly)
        limits.extend(patch.plane.height_at(*p)-clearance-line.base for p in poly)
    if not limits or abs(covered-_area(footprint))>max(EPS*10,_area(footprint)*1e-8):
        raise ValueError(f'{line.id}: wall is not fully covered by roof domains.')
    return min(limits)


def frame_sloping_wall(model, run, planes, *, object_id, floor_supports=(), detail=None):
    """Frame a mono-slope/gable wall below the minimum of top-cap planes.

    Planes are world-space *top of plate*, not roof top. The caller supplies
    roof-member clearance. The level wall height must reach every cap peak.
    Existing opening details are reused and rejected if a roof cut damages a
    header or jack. Valley-shaped caps need separate wall runs.
    """
    from .walls import plan_wall_members, FramingDetail
    from .wall_layout import layout_walls
    from .solids import prism
    from .stock import _below
    planes=tuple(planes)
    if not planes or any(not isinstance(p,Plane) or p.normal[2]<=EPS for p in planes):
        raise ValueError('Supply upward top-plate planes.')
    plan=plan_wall_members(layout_walls((run,)),detail=detail or FramingDetail())
    if plan.issues:raise ValueError('Resolve wall member/junction issues before applying a roof cap.')
    if any(p not in model.shapes for p in floor_supports):raise ValueError('Unknown sloping-wall floor support.')
    line=run.outside;dx,dy=line.end[0]-line.start[0],line.end[1]-line.start[1]
    length=math.hypot(dx,dy);ux,uy=dx/length,dy/length
    center=run.face('center');a,b=center.start,center.end
    # A cap is horizontal across its stock width. Use the lower roof height
    # there, so it cannot cross a roof that also slopes across the wall.
    caps=[]
    for plane in planes:
        h0=min(plane.height_at(a[0]-uy*d,a[1]+ux*d) for d in (-run.depth/2,run.depth/2))
        h1=min(plane.height_at(b[0]-uy*d,b[1]+ux*d) for d in (-run.depth/2,run.depth/2))
        slope=(h1-h0)/length
        caps.append(Plane.roof(origin=(*a,h0),slope=(ux*slope,uy*slope)))
    slopes=[(p.height_at(*b)-p.height_at(*a))/length for p in caps]
    if len(caps)>2 or (len(caps)==2 and abs(abs(slopes[0])-abs(slopes[1]))>EPS):
        raise ValueError('Use one slope or an equal-pitch gable; other cap junctions need an explicit detail.')
    cuts={0.,length}
    for p in caps:
        for q in caps:
            v=p.height_at(*a)-q.height_at(*a)
            den=(p.height_at(*b)-q.height_at(*b)-v)/length
            if abs(den)>EPS and EPS<-v/den<length-EPS:cuts.add(-v/den)
    stations=sorted(cuts);segments=[]
    for lo,hi in zip(stations,stations[1:]):
        x,y=a[0]+ux*(lo+hi)/2,a[1]+uy*(lo+hi)/2
        plane=min(caps,key=lambda p:p.height_at(x,y))
        if segments and segments[-1][2]==plane:segments[-1]=(segments[-1][0],hi,plane)
        else:segments.append((lo,hi,plane))
    peak=max(p.height_at(a[0]+ux*s,a[1]+uy*s) for lo,hi,p in segments for s in (lo,hi))
    if peak>line.base+run.height+EPS:raise ValueError('The source wall height must enclose the cap peak.')
    loc=cq.Plane(origin=(*line.start,line.base),xDir=(ux,uy,0),normal=(0,0,1)).location
    # Build all cuts before registration so impossible openings leave no partial wall.
    prepared=[];expected=[];top_contacts=[]
    for member in plan.members:
        if member.role.startswith('plate_top'):continue
        placement=loc*cq.Location(cq.Vector(*member.origin))
        original=prism(member.profile,member.size[2]);world=original.moved(placement)
        for plane in caps:world=_below(world,plane.offset(-2*run.thickness))
        if member.role in ('header','jack','sill') and original.Volume()-world.Volume()>EPS:
            raise ValueError(f'{member.id}: roof cap damages opening framing; revise its height or position.')
        pid=object_id+'.'+member.id
        if not world.Solids() or world.Volume()<EPS:
            if member.role!='cripple':raise ValueError(f'{member.id}: cap removes required wall framing.')
            continue
        expected.append(pid)
        local=world.moved(placement.inverse);size=list(member.size)
        vertical=member.role in ('stud','king','jack','cripple','pocket_stud')
        if vertical:size[2]=local.BoundingBox().zmax
        blank=dict(size=size,cut_length=size[2] if vertical else member.length,operations=[dict(kind='profile_cut',profile=member.profile),
            dict(kind='roof_cap',frame='world',planes=[dict(point=p.offset(-2*run.thickness).point,normal=p.normal) for p in caps])])
        prepared.append((pid,(local,placement,blank),member.section,member.product_id))
        if vertical and member.origin[2]+member.size[2]>=run.height-2*run.thickness-EPS:
            top_contacts.append((pid,prism(member.profile,1).Volume()))
    for i,(lo,hi,plane) in enumerate(segments):
        for course in range(2):
            top=plane.offset(-course*run.thickness)
            pa=(a[0]+ux*lo,a[1]+uy*lo);pb=(a[0]+ux*hi,a[1]+uy*hi)
            pid=object_id+f'.cap.s{i}.course{course}';expected.append(pid)
            prepared.append((pid,cut_member((*pa,top.height_at(*pa)),(*pb,top.height_at(*pb)),(run.depth,run.thickness)),(run.thickness,run.depth),None))
    model.assembly(object_id,'Roof-dependent wall')
    stock=StockParts(model,parent=object_id,demand_prefix=object_id+'.purchase.')
    parts=[]
    with model.batch():
        for pid,cut,section,product in prepared:
            stock.add(pid,cut,section=section,product_id=product);model.requirement(pid+'.valid','solid_valid',[pid]);parts.append(pid)
    for demand in stock.purchase(stock_lengths=plan.detail.stock_lengths,kerf=plan.detail.kerf):
        model.demands[demand]['unresolved'].extend(plan.detail.unresolved)
    model.requirement(object_id+'.clear','collision_free',parts)
    cap_parts=[p for p in parts if p.startswith(object_id+'.cap.')]
    for pid,area in top_contacts:model.requirement(pid+'.cap_contact','support',[pid,*cap_parts],threshold=area,direction=[0,0,1])
    conn=model.connection(object_id+'.details',parts=parts,description='Roof-cut studs and raking double plates with retained opening framing.',
        unresolved=[*plan.detail.unresolved,'Verify raking-plate joints, bracing, opening sizing, uplift and roof load transfer.'])
    for opening in run.openings:
        selected=opening.detail
        gaps=selected.unresolved+selected.header.unresolved
        if selected.pocket:gaps+=selected.pocket.unresolved
        if selected.transom:gaps+=selected.transom.header.unresolved
        model.connection(object_id+'.opening.'+opening.id,parts=parts,
            description='Retained opening specification below a sloping cap.',unresolved=list(gaps))
    for member in plan.members:
        pid=object_id+'.'+member.id
        if pid in parts and member.role=='plate_bottom' and floor_supports:
            model.requirement(pid+'.base','support',[pid,*floor_supports],threshold=prism(member.profile,1).Volume())
    model.expect(object_id+'.inventory',parts=expected,connections=[conn])
    return dict(parts=parts,plan=plan,cap_planes=tuple(caps))
