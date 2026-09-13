"""Stock-preserving operations for irregular framing and explicit design layouts.

These operations compose with MemberProfile, AnchorDetail and HangerDetail;
they do not infer a building footprint, structural products or span sizing.
"""
import math
import cadquery as cq
from .cad import point_at
from .solids import prism, round_member
from .stock import cut_panel


def _box(x,y,z,dx,dy,dz):
    return cq.Workplane('XY').box(dx,dy,dz,centered=(False,False,False)).val().translate((x,y,z))


def offset_polygon(poly,distance):
    """Intersect inward-offset edge lines, retaining the authored vertex order."""
    poly=list(poly)
    area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(poly,poly[1:]+poly[:1]))
    if len(poly)<3 or not math.isfinite(area) or abs(area)<1e-9:raise ValueError('A nondegenerate polygon is required.')
    sign=1 if area>0 else -1;lines=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        if length==0:raise ValueError('Repeated polygon vertex.')
        lines.append(((a[0]-sign*dy*distance/length,a[1]+sign*dx*distance/length),(dx,dy)))
    result=[]
    for (p,v),(q,w) in zip(lines[-1:]+lines[:-1],lines):
        cross=v[0]*w[1]-v[1]*w[0]
        if abs(cross)<1e-8:result.append(q);continue
        t=((q[0]-p[0])*w[1]-(q[1]-p[1])*w[0])/cross
        result.append((p[0]+t*v[0],p[1]+t*v[1]))
    return result


def polygon_intervals(poly,station):
    """Inside X intervals at a Y station; horizontal edges use a half-open rule."""
    poly=list(poly);hits=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        if (a[1]<=station<b[1]) or (b[1]<=station<a[1]):
            hits.append(a[0]+(station-a[1])*(b[0]-a[0])/(b[1]-a[1]))
    hits.sort()
    return list(zip(hits[::2],hits[1::2]))


def perimeter_stock(outline,profile,*,bottom,max_length,voids=()):
    """Miter and partition a perimeter band; return edge/piece identities and cuts.

    Tight returns are clipped to the footprint and preceding pieces so one
    physical region is never counted twice. Original rectangular blanks remain.
    X follows each board, Y crosses it; this is a panel-style stock frame.
    """
    if profile.flange or not math.isfinite(max_length) or max_length<=0:
        raise ValueError('Perimeter bands require solid stock and a positive cut limit.')
    poly=list(outline);width=profile.width;depth=profile.depth
    inner=offset_polygon(poly,width);used=[]
    boundary=prism(poly,depth,frame=cq.Plane(origin=(0,0,bottom),normal=(0,0,1)))
    for i,(a,b,c,d) in enumerate(zip(poly,poly[1:]+poly[:1],inner[1:]+inner[:1],inner)):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy);ux,uy=dx/length,dy/length
        frame=cq.Plane(origin=(*a,bottom),xDir=(ux,uy,0),normal=(0,0,1))
        points=[((p[0]-a[0])*ux+(p[1]-a[1])*uy,-(p[0]-a[0])*uy+(p[1]-a[1])*ux) for p in [a,b,c,d]]
        whole,placement,stock=cut_panel(frame,points,depth)
        if abs(stock['size'][1]-width)>1e-5:raise ValueError('Offset creates a perimeter piece wider than its stock.')
        count=max(1,math.ceil(stock['size'][0]/max_length))
        for j in range(count):
            x0=stock['size'][0]*j/count;length=stock['size'][0]/count
            local=whole.intersect(_box(x0,-1,-1,length,stock['size'][1]+2,depth+2)).clean()
            if local.Volume()<1e-6:continue
            local=local.translate((-x0,0,0));loc=placement*cq.Location(cq.Vector(x0,0,0))
            world=local.moved(loc).intersect(boundary)
            for previous in used:
                a0,b0=world.BoundingBox(),previous.BoundingBox()
                if a0.xmin<b0.xmax and a0.xmax>b0.xmin and a0.ymin<b0.ymax and a0.ymax>b0.ymin:world=world.cut(previous)
            if not world.Solids():continue
            used.append(world)
            for void in voids:world=world.cut(void)
            local=world.moved(loc.inverse).clean()
            if not local.Solids():continue
            operations=[]
            for face in local.Faces():
                if face.normalAt().z>-.99:continue
                operations.append(dict(kind='profile_cut',profile=[(v.X,v.Y) for v in face.outerWire().Vertices()],
                    holes=[[(v.X,v.Y) for v in wire.Vertices()] for wire in face.innerWires()],
                    note='Finished perimeter outline in this piece\'s original stock axes.'))
            blank=dict(size=[length,width,depth],cut_length=length,operations=operations)
            yield i,j,(local,loc,blank)


def clipped_member(profile,start,end,*,boundary=None,voids=()):
    """Cut real solid/I stock, then trim it against a boundary and named voids."""
    shape,location,blank=profile.cut(start,end)
    world=shape.moved(location)
    if boundary is not None:world=world.intersect(boundary)
    for void in voids:world=world.cut(void)
    world=world.clean()
    if not world.Solids() or world.Volume()<1e-4:return None
    if len(world.Solids())>1:raise ValueError('A clipped member must remain one physical solid; split its layout first.')
    local=world.moved(location.inverse)
    if boundary is not None or voids:
        face=next(f for f in local.Faces() if f.normalAt().z<-.99)
        outline=[(v.X,v.Y) for v in face.outerWire().Vertices()]
        blank['operations'].append(dict(kind='profile_cut',profile=outline,
            note='Trimmed to the authored boundary and opening voids in original stock.'))
    return local,location,blank


def drill_anchor_pattern(shape,location,*,width,depth,length,detail,max_spacing,end_distance,
                         min_end,shifts=(0,),cross_shifts=(0,),accept=None):
    """Retain a specified evenly divided pattern while adapting around obstacles.

    `accept(world_bottom_point)` is optional project layout policy. Every bore
    must be fully contained in the actual sill. Returns original station keys,
    allowing deliberate exceptions and existing review IDs to survive refactoring.
    Use anchor_layout for a newly solved minimum-count pattern.
    """
    if min(width,depth,length,max_spacing,min_end)<=0 or not 0<end_distance<=length/2:
        raise ValueError('Anchor pattern dimensions/end offset must fit the sill.')
    count=max(2,math.ceil(max(0,length-2*end_distance)/max_spacing)+1)
    world=shape.moved(location);points=[];bores=[]
    for k in range(count):
        station=end_distance+(length-2*end_distance)*k/(count-1)
        found=None
        for shift in shifts:
            for across in cross_shifts:
                if not min_end<=station+shift<=length-min_end:continue
                if (k==0 and shift>0) or (k==count-1 and shift<0):continue
                x,y,z=point_at(location,(station+shift,width/2+across,0))
                if accept and not accept((x,y,z)):continue
                bore=round_member((x,y,z-.1),(x,y,z+depth+.1),detail.hole_diameter)
                if abs(bore.intersect(world).Volume()-math.pi*(detail.hole_diameter/2)**2*depth)>.0001:continue
                found=(x,y,z,bore);break
            if found:break
        if found:
            x,y,z,bore=found;bores.append(bore);points.append((k,x,y,z))
    for bore in bores:world=world.cut(bore)
    return world.moved(location.inverse).clean(),points


def bearing_contacts(world,supports,*,probe_depth=.01):
    """Discover contact candidates; callers declare native support requirements."""
    contacts=[];bb=world.BoundingBox()
    for pid,shape in supports.items():
        sb=shape.BoundingBox()
        if bb.xmax<sb.xmin or bb.xmin>sb.xmax or bb.ymax<sb.ymin or bb.ymin>sb.ymax:continue
        area=world.translate((0,0,-probe_depth)).intersect(shape).Volume()/probe_depth
        if area>.01:contacts.append((pid,area))
    return contacts


def member_end_interfaces(world,start,end,width,supports,framing,*,member_id,min_bearing=1.5):
    """Resolve each end's actual seat or adjacent face-mounted host separately."""
    axis=(cq.Vector(*end)-cq.Vector(*start)).normalized()
    for k,point in enumerate((start,end)):
        toward=axis if k==0 else -axis;outside=-toward
        across=toward.cross(cq.Vector(0,0,1))
        location=cq.Plane(origin=cq.Vector(*point)-across*(width/2),xDir=across,normal=(0,0,1)).location
        zone=_box(0,0,-.01,width,min_bearing,.01).moved(location)
        area=0;contacts=[]
        for pid,shape in supports.items():
            bb,sb=zone.BoundingBox(),shape.BoundingBox()
            if bb.xmin>sb.xmax or bb.xmax<sb.xmin or bb.ymin>sb.ymax or bb.ymax<sb.ymin:continue
            overlap=zone.intersect(shape).Volume()/.01
            if overlap>.01:area+=overlap;contacts.append(pid)
        result=dict(end=k,location=location,bearing_area=area,supports=contacts)
        if area>=width*min_bearing-.01:
            yield result;continue
        moved=world.translate((outside.x*.02,outside.y*.02,0));hosts=[]
        for pid,shape in framing.items():
            if pid==member_id:continue
            bb,sb=moved.BoundingBox(),shape.BoundingBox()
            if bb.xmin>sb.xmax or bb.xmax<sb.xmin or bb.ymin>sb.ymax or bb.ymax<sb.ymin:continue
            overlap=moved.intersect(shape).Volume()
            if overlap>.01:hosts.append((overlap,pid))
        if hosts:result['host']=max(hosts)[1]
        else:result['unresolved']='Insufficient end bearing and no face-mounted host'
        yield result
