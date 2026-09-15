"""Explicit, unengineered factory-truss geometry from a vertical roof profile.

The caller selects every stock size, bearing inset, panel interval and plate
size. This is a geometric composition, not a truss analysis or shop schedule.
"""
import math
import cadquery as cq
from .stock import Plane, cut_member
from .roof_layout import EPS


def centered_member(a,b,section, *, normal, cuts=()):
    """Rectangular member around a centerline, with caller-owned end cuts."""
    a,b,n=map(cq.Vector,(a,b,normal));axis=(b-a).normalized()
    up=n.cross(axis).normalized()
    sp=Plane(a.toTuple(),(-axis).toTuple());ep=Plane(b.toTuple(),axis.toTuple())
    start=[p for p in cuts if cq.Vector(p.normal).dot(axis)<-EPS]
    end=[p for p in cuts if cq.Vector(p.normal).dot(axis)>EPS]
    if start:sp=min(start,key=lambda p:abs(p.signed_distance(a.toTuple())))
    if end:ep=min(end,key=lambda p:abs(p.signed_distance(b.toTuple())))
    offset=up*(section[1]/2)
    return cut_member((a+offset).toTuple(),(b+offset).toTuple(),section,
                      start_plane=sp,end_plane=ep,top_planes=cuts,up=up.toTuple())


def incident_miters(segments, *, tolerance=1e-6):
    """Bisect equal-width member nodes in their common plane.

    Returns one tuple of outward cut planes per segment. Centerline endpoints
    are explicit; this does not infer a joint at crossing or near-miss members.
    Collinear continuation is a square butt. Different stock depths may need
    additional project detailing; cuts partition node footprints, not loads.
    """
    lines=tuple((cq.Vector(a),cq.Vector(b)) for a,b in segments)
    if any((b-a).Length<tolerance for a,b in lines):raise ValueError('Joint segments need length.')
    result=[]
    for i,(a,b) in enumerate(lines):
        cuts=[]
        for node,other in ((a,b),(b,a)):
            u=(other-node).normalized()
            for j,(c,d) in enumerate(lines):
                if i==j:continue
                if (node-c).Length<=tolerance:v=(d-c).normalized()
                elif (node-d).Length<=tolerance:v=(c-d).normalized()
                else:continue
                normal=v-u
                if normal.Length<tolerance:raise ValueError('Coincident member rays need a through-member detail.')
                cuts.append(Plane(node.toTuple(),normal.toTuple()))
        result.append(tuple(cuts))
    return tuple(result)


def frame_profile_truss(model, profile, *, object_id, bottom, chord_section,
                        web_section, panel_length, bearing_insets, plate_size,
                        parent=None, unresolved=()):
    """Build selected chords, triangulated panels and generic plate envelopes.

    profile is a continuous planar RoofSegment chain. bottom is the bottom of
    the bottom chord. bearing_insets trim that chord inward from profile ends.
    Explicit assumptions persist on the factory demand and each part's lineage.
    No lumber purchase/cut list or structural-capacity claim is generated.
    """
    profile=tuple(profile);cw,cd=chord_section;ww,wd=web_section;pw,ph,pt=plate_size
    bearing_insets=tuple(bearing_insets)
    if len(bearing_insets)!=2:raise ValueError('Supply one bearing inset at each profile end.')
    values=(bottom,cw,cd,ww,wd,panel_length,*bearing_insets,pw,ph,pt)
    if not profile or not all(math.isfinite(v) for v in values) or min(cw,cd,ww,wd,panel_length,pw,ph,pt)<=0 or min(bearing_insets)<0:
        raise ValueError('Select a continuous profile and finite positive truss dimensions.')
    if abs(cw-ww)>EPS:raise ValueError('Chords and webs need the same truss thickness.')
    if any(math.dist(a.end,b.start)>1e-5 for a,b in zip(profile,profile[1:])):raise ValueError('A truss cannot span a missing profile region.')
    origin=cq.Vector(*profile[0].start);last=cq.Vector(*profile[-1].end)
    direction=cq.Vector(last.x-origin.x,last.y-origin.y,0)
    if direction.Length<EPS:raise ValueError('Truss needs a horizontal span.')
    length=direction.Length;u=direction.normalized();n=u.cross(cq.Vector(0,0,1))
    def point(x,z):return (origin.x+u.x*x,origin.y+u.y*x,z)
    raw=[]
    for s in profile:
        for p in (s.start,s.end):
            delta=cq.Vector(*p)-origin
            if abs(delta.dot(n))>1e-5:raise ValueError('Truss profile must lie in one vertical plane.')
            v=(delta.dot(u),p[2])
            if not raw or math.dist(v,raw[-1])>EPS:raw.append(v)
    if any(b[0]<=a[0]+EPS for a,b in zip(raw,raw[1:])):raise ValueError('Truss profile must advance along its span.')
    # Coalesce numerical patch breaks on the same physical chord.
    points=[]
    for p in raw:
        while len(points)>1:
            a,b=points[-2:]
            if abs((b[1]-a[1])*(p[0]-b[0])-(p[1]-b[1])*(b[0]-a[0]))>1e-5:break
            points.pop()
        points.append(p)
    lo,hi=bearing_insets[0],length-bearing_insets[1]
    if hi-lo<=2*cd:raise ValueError('Bearing insets leave no useful truss span.')
    def height(x):
        for (a,z),(b,h) in zip(points,points[1:]):
            if a-EPS<=x<=b+EPS:return z+(h-z)*(x-a)/(b-a)
        raise ValueError('Panel station outside truss profile.')
    # Chords follow the actual top plane, full section below. Vertical miter
    # planes at profile breaks preserve the roof surface without overlap.
    prepared=[];tops=[]
    for i,(a,b) in enumerate(zip(points,points[1:])):
        cut=cut_member(point(*a),point(*b),chord_section)
        world=cut[0].moved(cut[1]);tops.append(world)
        prepared.append((f'top.{i}',cut,'top_chord'))
    bottom_cut=cut_member(point(lo,bottom+cd),point(hi,bottom+cd),chord_section)
    shape,loc,blank=bottom_cut;world=shape.moved(loc)
    for t in tops:world=world.cut(t)
    world=world.clean()
    if len(world.Solids())!=1:raise ValueError('Top profile severs bottom chord; revise heel or bearing insets.')
    blank={**blank,'operations':[*blank['operations'],dict(kind='truss_heel_joint',profile=points)]}
    prepared.append(('bottom',(world.moved(loc.inverse),loc,blank),'bottom_chord'));chords=[*tops,world]
    # Verticals at panel stations and diagonals toward the high point create a
    # triangulated Pratt-style conceptual layout, including truncated hip tops.
    anchors=[lo,*[x for x,z in points[1:-1] if lo+pw*2<x<hi-pw*2],hi]
    anchors=sorted(set(anchors));stations=[lo]
    for a,b in zip(anchors,anchors[1:]):
        count=max(1,math.ceil((b-a)/panel_length))
        stations.extend(a+(b-a)*i/count for i in range(1,count+1))
    nodes={};webs=[]
    for i,x in enumerate(stations):
        nodes[f'b{i}']=point(x,bottom+cd/2)
        nodes[f't{i}']=point(x,height(x)-cd/2)
        if height(x)-bottom>2*cd+wd:webs.append((f'vertical.{i}',f'b{i}',f't{i}'))
    peak=max(points,key=lambda p:p[1])[0]
    for i,(a,b) in enumerate(zip(stations,stations[1:])):
        if min(height(a),height(b))-bottom<=2*cd+wd:continue
        webs.append((f'diagonal.{i}',f'b{i}' if (a+b)/2<peak else f't{i}',f't{i+1}' if (a+b)/2<peak else f'b{i+1}'))
    lines=[(nodes[a],nodes[b]) for key,a,b in webs];miters=incident_miters(lines)
    cavity_pieces=[]
    frame=cq.Plane(origin=point(0,0),xDir=u,normal=n)
    for a,b in zip(points,points[1:]):
        drop=cd*math.sqrt(1+((b[1]-a[1])/(b[0]-a[0]))**2)
        za,zb=a[1]-drop,b[1]-drop;floor=bottom+cd
        xa,xb=a[0],b[0]
        if max(za,zb)<=floor:continue
        if za<floor:xa+=(floor-za)*(xb-xa)/(zb-za);za=floor
        if zb<floor:xb=xa+(floor-za)*(xb-xa)/(zb-za);zb=floor
        poly=[(xa,floor),(xb,floor),(xb,zb),(xa,za)]
        clean=[]
        for p in poly:
            if not clean or math.dist(p,clean[-1])>EPS:clean.append(p)
        if len(clean)>2 and math.dist(clean[0],clean[-1])<EPS:clean.pop()
        cavity_pieces.append(cq.Workplane(frame).polyline(clean).close().extrude(cw,both=True).val())
    if not cavity_pieces:raise ValueError('Truss has no web cavity above its bottom chord.')
    cavity=cavity_pieces[0].fuse(*cavity_pieces[1:]).clean() if len(cavity_pieces)>1 else cavity_pieces[0]
    for (key,a,b),cuts in zip(webs,miters):
        shape,loc,blank=centered_member(nodes[a],nodes[b],web_section,normal=n.toTuple(),cuts=cuts)
        world=shape.moved(loc)
        for chord in chords:world=world.cut(chord)
        world=world.intersect(cavity).clean()
        if len(world.Solids())!=1:raise ValueError(f'{key}: joint cuts sever web; revise panel layout.')
        blank={**blank,'operations':[*blank['operations'],dict(kind='factory_chord_butt',members=['top','bottom'])]}
        prepared.append((key,(world.moved(loc.inverse),loc,blank),'web'))
    # Plates are deliberately simple clipped metal envelopes on both faces.
    # Clip them to the outer roof/ceiling profile so they do not project above
    # framing or below the ceiling. Teeth and manufacturer sizing are omitted.
    # Using the convex pieces of the roof band also supports non-convex profiles.
    masks=[]
    for a,b in zip(points,points[1:]):
        if max(a[1],b[1])<=bottom:continue
        xa,za=a;xb,zb=b
        if za<bottom:xa+=(bottom-za)*(xb-xa)/(zb-za);za=bottom
        if zb<bottom:xb=xa+(bottom-za)*(xb-xa)/(zb-za);zb=bottom
        clean=[]
        for p in ((xa,bottom),(xb,bottom),(xb,zb),(xa,za)):
            if not clean or math.dist(p,clean[-1])>EPS:clean.append(p)
        if math.dist(clean[0],clean[-1])<EPS:clean.pop()
        frame=cq.Plane(origin=point(0,0),xDir=u,normal=n)
        masks.append(cq.Workplane(frame).polyline(clean).close().extrude(cw+2*pt,both=True).val())
    for i,(x,z) in enumerate(points[1:-1]):
        node=point(x,z-cd/2)
        if lo<x<hi and not any(math.dist(node,v)<EPS for v in nodes.values()):nodes[f'joint{i}']=node
    plates=[]
    for key,v in nodes.items():
        if key.startswith('t') and int(key[1:]) in (0,len(stations)-1):continue
        x=(cq.Vector(*v)-origin).dot(u);z=v[2]
        for side in (-1,1):
            frame=cq.Plane(origin=cq.Vector(*point(x,z))+n*(side*cw/2),xDir=u,normal=n*side)
            plate=cq.Workplane(frame).rect(pw,ph).extrude(pt).val()
            pieces=[plate.intersect(mask) for mask in masks]
            pieces=[p for p in pieces if p.Volume()>EPS]
            if not pieces:continue
            plate=pieces[0].fuse(*pieces[1:]).clean() if len(pieces)>1 else pieces[0]
            plates.append((f'plate.{key}.{side}',plate))
    model.assembly(object_id,'Assumed factory truss',parent=parent)
    parts=[];timber=[]
    assumptions=dict(representation='assumed_factory_members',chord_section=list(chord_section),web_section=list(web_section),panel_length=panel_length,bearing_insets=list(bearing_insets),plate_size=list(plate_size))
    with model.batch():
        for key,(shape,loc,blank),role in prepared:
            pid=object_id+'.'+key
            model.part(pid,shape,location=loc,parent=object_id,material='factory.truss.assumed.timber',blank=blank,
                       label='Assumed truss '+role.replace('_',' '),lineage={**assumptions,'role':role})
            model.requirement(pid+'.valid','solid_valid',[pid]);model.requirement(pid+'.stock','stock_fit',[pid]);parts.append(pid);timber.append(pid)
        for key,shape in plates:
            pid=object_id+'.'+key
            model.part(pid,shape,parent=object_id,material='factory.truss.assumed.plate',color='#8d979d',label='Assumed truss connector plate',lineage=assumptions)
            model.requirement(pid+'.valid','solid_valid',[pid]);parts.append(pid)
    model.requirement(object_id+'.timber_clear','collision_free',timber)
    top_ids=[object_id+'.'+key for key,_,role in prepared if role=='top_chord']
    for key,_,role in prepared:
        if role!='web':continue
        pid=object_id+'.'+key
        model.requirement(pid+'.lower_joint','support',[pid,object_id+'.bottom'],threshold=0)
        model.requirement(pid+'.upper_joint','support',[pid,*top_ids],threshold=0,direction=[0,0,1])
    gaps=['Conceptual truss geometry explicitly uses assumed members and plate envelopes; manufacturer must design sections, joints, reactions, restraint and bracing.',*unresolved]
    model.demand(object_id+'.factory',product_id='factory.truss.assumed',specification={**assumptions,'bottom':bottom,'profile':points,'status':'unengineered model'},object_ids=parts,quantity=1,unit='truss',purchase_unit='truss',unresolved=gaps)
    model.connection(object_id+'.design_basis',parts=parts,description='User-authorized assumed factory-truss framing, with triangulated panels.',unresolved=gaps)
    model.expect(object_id+'.inventory',parts=parts)
    return dict(parts=parts,timber=timber,profile=profile)
