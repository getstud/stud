"""Named, immutable roof planes and their visible plan domains.

Resolve geometry again when Python inputs change. This module does not choose
structural systems, members, connections, loads, or manufacturer truss designs.
Convex domains are deliberate: compose concave roofs from convex components.
"""
from dataclasses import dataclass
import math

from .stock import Plane

EPS = 1e-7


def _area(poly):
    return sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(poly,poly[1:]+poly[:1]))/2


def _clean(poly):
    result=[]
    for p in poly:
        p=tuple(p)
        if not result or math.dist(p,result[-1])>EPS:result.append(p)
    if len(result)>1 and math.dist(result[0],result[-1])<EPS:result.pop()
    if len(result)<3 or abs(_area(result))<EPS:return ()
    return tuple(result if _area(result)>0 else reversed(result))


def clip_polygon(poly, normal, offset):
    """Keep n·XY <= offset; empty intersections return an empty tuple."""
    out=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        da=sum(x*y for x,y in zip(normal,a))-offset
        db=sum(x*y for x,y in zip(normal,b))-offset
        if da<=EPS:out.append(a)
        if (da<0<db or db<0<da) and abs(da-db)>EPS:
            t=da/(da-db);out.append(tuple(x+t*(y-x) for x,y in zip(a,b)))
    return _clean(out)


def boundary_planes(poly):
    """Outward unit XY normals and offsets of a counterclockwise domain."""
    result=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        if length>EPS:
            n=(dy/length,-dx/length);result.append((n,n[0]*a[0]+n[1]*a[1]))
    return tuple(result)


def _coeff(plane):
    x,y,z=plane.normal
    return -x/z,-y/z,plane.height_at(0,0)


def _subtract(poly, cutter):
    common=poly
    for n,d in boundary_planes(cutter):
        common=clip_polygon(common,n,d)
        if not common:return [poly]
    outside=[];inside=poly
    for n,d in boundary_planes(cutter):
        piece=clip_polygon(inside,(-n[0],-n[1]),-d)
        if piece:outside.append(piece)
        inside=clip_polygon(inside,n,d)
        if not inside:break
    return outside


def _coalesce(pieces):
    def hull(points):
        def cross(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
        points=sorted(set(points));lower=[];upper=[]
        for p in points:
            while len(lower)>=2 and cross(lower[-2],lower[-1],p)<=EPS:lower.pop()
            lower.append(p)
        for p in reversed(points):
            while len(upper)>=2 and cross(upper[-2],upper[-1],p)<=EPS:upper.pop()
            upper.append(p)
        return tuple(lower[:-1]+upper[:-1])
    pieces=list(pieces)
    while True:
        merged=False
        for i,a in enumerate(pieces):
            for j in range(i+1,len(pieces)):
                b=pieces[j];whole=hull((*a,*b))
                if abs(_area(whole)-_area(a)-_area(b))<EPS:
                    pieces[i]=whole;pieces.pop(j);merged=True;break
            if merged:break
        if not merged:return pieces


@dataclass(frozen=True)
class RoofFace:
    """Top of framing, its convex XY domain, and a stable semantic identity."""
    id: str
    plane: Plane
    outline: tuple

    def __post_init__(self):
        try:
            points=tuple(tuple(p) for p in self.outline)
            valid=all(len(p)==2 and all(math.isfinite(v) for v in p) for p in points)
        except (TypeError,ValueError):valid=False
        if not valid or not self.id or not isinstance(self.plane,Plane) or self.plane.normal[2]<=EPS:
            raise ValueError('A roof face needs a name, upward plane and finite XY polygon.')
        points=_clean(points)
        if not points or any(sum(x*y for x,y in zip(n,p))>d+EPS for n,d in boundary_planes(points) for p in points):
            raise ValueError('Roof domains must be nondegenerate convex polygons.')
        object.__setattr__(self,'outline',points)

    def contains(self,x,y):
        return all(n[0]*x+n[1]*y<=d+EPS for n,d in boundary_planes(self.outline))


def hip_roof_faces(object_id, outline, *, eave_top, pitch):
    """Equal pitch hip/pyramid over a convex *eave* outline, not wall centers.

    eave_top is top of framing. Horizontal overhang, heel and seat allowances
    must already be resolved by the caller. Return independent named faces.
    """
    if not math.isfinite(eave_top) or not math.isfinite(pitch) or pitch<=0:
        raise ValueError('Hip roofs need a finite eave elevation and positive rise/run.')
    domain=RoofFace(object_id,Plane.roof(),outline).outline
    planes=[Plane.roof(origin=(*a,eave_top),slope=(-n[0]*pitch,-n[1]*pitch))
            for a,(n,d) in zip(domain,boundary_planes(domain))]
    faces=[]
    for i,plane in enumerate(planes):
        poly=domain;a,b,c=_coeff(plane)
        for other in planes:
            x,y,z=_coeff(other);poly=clip_polygon(poly,(a-x,b-y),z-c)
            if not poly:break
        if poly:faces.append(RoofFace(f'{object_id}.face{i}',plane,poly))
    return tuple(faces)


def gable_roof_faces(object_id, start, end, *, half_span, eave_top, pitch):
    """Symmetric gable with a horizontal ridge from XY start to XY end.

    Endpoints and half_span describe the roof perimeter, including any selected
    overhangs. eave_top is top of framing, not wall top. Faces have stable
    ``.left`` / ``.right`` IDs looking from start toward end. Pitch is rise/run;
    each composed component owns its own pitch. This does not select bearings,
    heels, end-wall framing or a structural system.
    """
    start,end=tuple(start),tuple(end)
    if (len(start)!=2 or len(end)!=2 or
        not all(math.isfinite(v) for v in (*start,*end,half_span,eave_top,pitch)) or
        half_span<=0 or pitch<=0 or math.dist(start,end)<EPS):
        raise ValueError('A gable needs distinct finite XY ridge endpoints, positive half-span and pitch, and a finite eave elevation.')
    length=math.dist(start,end)
    normal=(-(end[1]-start[1])/length,(end[0]-start[0])/length)
    faces=[]
    for side,sign in (('left',1),('right',-1)):
        a=tuple(p+sign*half_span*n for p,n in zip(start,normal))
        b=tuple(p+sign*half_span*n for p,n in zip(end,normal))
        plane=Plane.roof(origin=(*a,eave_top),slope=tuple(-sign*pitch*n for n in normal))
        faces.append(RoofFace(f'{object_id}.{side}',plane,(start,end,b,a)))
    return tuple(faces)


@dataclass(frozen=True)
class RoofSegment:
    face: str
    start: tuple
    end: tuple


@dataclass(frozen=True)
class RoofLayout:
    faces: tuple
    patches: tuple

    def __post_init__(self):
        object.__setattr__(self,'faces',tuple(self.faces))
        object.__setattr__(self,'patches',tuple(self.patches))

    def height_at(self,x,y):
        """Visible roof top, or None outside all domains."""
        heights=[f.plane.height_at(x,y) for f in self.faces if f.contains(x,y)]
        return max(heights) if heights else None

    def section(self,start,end):
        """Visible roof profile along an XY segment, split at face boundaries.

        Gaps stay gaps; this never bridges missing domains. Profiles can drive
        roof-dependent walls and factory truss coordination independently.
        """
        start,end=tuple(start),tuple(end)
        if len(start)!=2 or len(end)!=2 or not all(math.isfinite(x) for x in (*start,*end)) or math.dist(start,end)<EPS:
            raise ValueError('A roof section needs distinct finite XY endpoints.')
        dx,dy=end[0]-start[0],end[1]-start[1];cuts={0.,1.}
        for face in self.patches:
            for n,d in boundary_planes(face.outline):
                den=n[0]*dx+n[1]*dy
                if abs(den)>EPS:
                    t=(d-n[0]*start[0]-n[1]*start[1])/den
                    if EPS<t<1-EPS:cuts.add(t)
        result=[]
        stations=sorted(cuts)
        for lo,hi in zip(stations,stations[1:]):
            if hi-lo<EPS:continue
            t=(lo+hi)/2;x,y=start[0]+dx*t,start[1]+dy*t
            candidates=[f for f in self.faces if f.contains(x,y)]
            if not candidates:continue
            face=max(candidates,key=lambda f:(f.plane.height_at(x,y),f.id))
            a=(start[0]+dx*lo,start[1]+dy*lo);b=(start[0]+dx*hi,start[1]+dy*hi)
            a=(*a,face.plane.height_at(*a));b=(*b,face.plane.height_at(*b))
            if result and result[-1].face==face.id and math.dist(result[-1].end,a)<EPS:
                result[-1]=RoofSegment(face.id,result[-1].start,b)
            else:result.append(RoofSegment(face.id,a,b))
        return tuple(result)


def layout_roofs(faces):
    """Clip overlapping components to their upper envelope before framing.

    Coplanar overlaps have one deterministic owner (lexicographically larger
    ID), independent of input order. Original input faces are retained.
    """
    faces=tuple(sorted(faces,key=lambda f:f.id))
    if not faces or len({f.id for f in faces})!=len(faces):
        raise ValueError('Provide roof faces with unique IDs.')
    patches=[]
    for face in faces:
        pieces=[face.outline];a,b,c=_coeff(face.plane)
        for other in faces:
            if other.id==face.id:continue
            x,y,z=_coeff(other.plane)
            if max(abs(a-x),abs(b-y),abs(c-z))<EPS:
                if other.id<face.id:continue
                cutter=other.outline
            else:cutter=clip_polygon(other.outline,(a-x,b-y),z-c)
            if cutter:
                pieces=[p for piece in pieces for p in _subtract(piece,cutter)]
            if not pieces:break
        patches.extend(RoofFace(face.id,face.plane,p) for p in _coalesce(pieces))
    return RoofLayout(faces,tuple(patches))


def roof_stations(layout, *, direction, spacing, origin=(0,0)):
    """Stable integer stations and visible profiles, suitable for truss setout.

    direction is a horizontal member axis. Spacing is measured perpendicular
    to it. No default truss spacing or web arrangement is inferred.
    """
    dx,dy=direction;length=math.hypot(dx,dy)
    if not all(math.isfinite(v) for v in (*direction,*origin,spacing)) or length<EPS or spacing<=0:
        raise ValueError('Station layout needs a direction, origin and positive spacing.')
    dx,dy=dx/length,dy/length;nx,ny=-dy,dx
    points=[(p[0]-origin[0],p[1]-origin[1]) for f in layout.faces for p in f.outline]
    rows=[nx*x+ny*y for x,y in points];along=[dx*x+dy*y for x,y in points]
    result=[]
    for k in range(math.ceil((min(rows)+EPS)/spacing),math.floor((max(rows)-EPS)/spacing)+1):
        def at(s):return (origin[0]+nx*k*spacing+dx*s,origin[1]+ny*k*spacing+dy*s)
        profile=layout.section(at(min(along)),at(max(along)))
        if profile:result.append((k,profile))
    return tuple(result)


@dataclass(frozen=True)
class RoofEdge:
    faces: tuple
    start: tuple
    end: tuple
    kind: str


def roof_boundary_edges(layout):
    """Exposed eave, rake and upper step edges of the visible roof envelope.

    Split at adjacent patch boundaries before classifying. Internal seams are
    excluded. A lower roof beside an edge makes it a ``step``, not an eave;
    this is geometry evidence, not an inferred fascia or flashing detail.
    Start/end order follows the owning counterclockwise patch, with roof
    interior to the left. Rakes are sloping boundaries; this alone does not
    establish a gable or a lookout support.
    """
    result={}
    for face in layout.patches:
        for a,b in zip(face.outline,face.outline[1:]+face.outline[:1]):
            dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
            cuts={0.,1.}
            for other in layout.patches:
                for n,d in boundary_planes(other.outline):
                    den=n[0]*dx+n[1]*dy
                    if abs(den)>EPS:
                        t=(d-n[0]*a[0]-n[1]*a[1])/den
                        if EPS<t<1-EPS:cuts.add(t)
            stations=sorted(cuts)
            pieces=[]
            for lo,hi in zip(stations,stations[1:]):
                if (hi-lo)*length<EPS*10:continue
                t=(lo+hi)/2;mid=(a[0]+t*dx,a[1]+t*dy)
                z=face.plane.height_at(*mid)
                # Symbolic outward limit: membership on a boundary counts only
                # when stepping outward enters (rather than leaves) that face.
                outward=(dy/length,-dx/length);neighbors=[]
                for other in layout.patches:
                    if all(n[0]*mid[0]+n[1]*mid[1]<d-EPS or
                           (n[0]*mid[0]+n[1]*mid[1]<=d+EPS and n[0]*outward[0]+n[1]*outward[1]<=EPS)
                           for n,d in boundary_planes(other.outline)):
                        neighbors.append(other.plane.height_at(*mid))
                outside=max(neighbors) if neighbors else None
                if outside is not None and outside>=z-EPS:continue
                p=(a[0]+lo*dx,a[1]+lo*dy);q=(a[0]+hi*dx,a[1]+hi*dy)
                p=(*p,face.plane.height_at(*p));q=(*q,face.plane.height_at(*q))
                kind='step' if outside is not None else ('eave' if abs(p[2]-q[2])<EPS else 'rake')
                if pieces and pieces[-1].kind==kind and math.dist(pieces[-1].end,p)<EPS:
                    pieces[-1]=RoofEdge((face.id,),pieces[-1].start,q,kind)
                else:pieces.append(RoofEdge((face.id,),p,q,kind))
            for edge in pieces:
                p,q=edge.start,edge.end
                key=(face.id,tuple(tuple(round(v,7) for v in x) for x in (p,q)))
                result[key]=edge
    return tuple(result[k] for k in sorted(result))


def roof_edges(layout):
    """Finite shared ridge/hip/valley/break edges of visible roof patches.

    Coincident XY boundaries at different elevations are not roof joints.
    Exterior eaves and roof-to-wall steps are intentionally not inferred here.
    """
    segments={}
    for i,face in enumerate(layout.patches):
        for other in layout.patches[i+1:]:
            if face.id==other.id or max(abs(a-b) for a,b in zip(_coeff(face.plane),_coeff(other.plane)))<EPS:continue
            for a,b in zip(face.outline,face.outline[1:]+face.outline[:1]):
                length=math.dist(a,b);u=((b[0]-a[0])/length,(b[1]-a[1])/length);n=(-u[1],u[0])
                for c,d in zip(other.outline,other.outline[1:]+other.outline[:1]):
                    if any(abs((p[0]-a[0])*n[0]+(p[1]-a[1])*n[1])>EPS*10 for p in (c,d)):continue
                    values=[(p[0]-a[0])*u[0]+(p[1]-a[1])*u[1] for p in (c,d)]
                    lo,hi=max(0,min(values)),min(length,max(values))
                    if hi-lo<EPS*10:continue
                    p=(a[0]+u[0]*lo,a[1]+u[1]*lo);q=(a[0]+u[0]*hi,a[1]+u[1]*hi)
                    if any(abs(face.plane.height_at(*v)-other.plane.height_at(*v))>EPS*10 for v in (p,q)):continue
                    mid=((p[0]+q[0])/2,(p[1]+q[1])/2);changes=[]
                    for f in (face,other):
                        center=tuple(sum(v[k] for v in f.outline)/len(f.outline) for k in (0,1))
                        sign=1 if (center[0]-mid[0])*n[0]+(center[1]-mid[1])*n[1]>0 else -1
                        changes.append(f.plane.height_at(mid[0]+sign*n[0],mid[1]+sign*n[1])-f.plane.height_at(*mid))
                    kind='valley' if min(changes)>EPS else 'break'
                    if max(changes)<-EPS:kind='ridge' if abs(face.plane.height_at(*p)-face.plane.height_at(*q))<EPS else 'hip'
                    ends=tuple(sorted(((*p,face.plane.height_at(*p)),(*q,face.plane.height_at(*q)))))
                    key=(tuple(sorted((face.id,other.id))),tuple(tuple(round(v,6) for v in p) for p in ends))
                    segments[key]=RoofEdge(key[0],*ends,kind)
    return tuple(segments[k] for k in sorted(segments))
