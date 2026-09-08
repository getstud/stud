"""Convex solid geometry shared by validation rules. Coordinates are inches.
Supports boxes, linear Y/Z profiles, stepped gable notches and world-Y/Z seats.
Euler rotations match Three.js XYZ (Rz applied first to local coordinates).
"""
import math
from profile_geometry import triangulate_outline, validate_bands, validate_layers
from itertools import combinations

EPS = 1e-7


def add(a,b): return tuple(x+y for x,y in zip(a,b))
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def mul(a,s): return tuple(x*s for x in a)
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def norm(a): return math.sqrt(dot(a,a))
def unit(a): return mul(a,1/norm(a)) if norm(a)>EPS else (0,0,0)
def mean(vs): return tuple(sum(v[i] for v in vs)/len(vs) for i in range(3))


def unique(vs):
    result=[]
    for v in vs:
        if not any(norm(sub(v,w))<EPS for w in result):result.append(v)
    return result


def normal(face):
    for i in range(1,len(face)-1):
        n=cross(sub(face[i],face[0]),sub(face[i+1],face[0]))
        if norm(n)>EPS:return unit(n)
    return (0,0,0)


def clean(faces):
    points=unique([v for f in faces for v in f])
    if len(points)<4:return []
    center=mean(points);result=[]
    for face in faces:
        face=unique(face);n=normal(face)
        if norm(n)<EPS:continue
        if dot(n,sub(mean(face),center))<0:face.reverse()
        result.append(face)
    return result if volume(result)>EPS else []


def volume(faces):
    # Translation-independent tetrahedra about an interior point.
    if not faces:return 0
    center=mean([v for f in faces for v in f])
    return sum(abs(dot(sub(f[0],center),cross(sub(f[i],center),sub(f[i+1],center))))/6 for f in faces for i in range(1,len(f)-1))


def prism(x0,x1,d,bottom,top):
    bf,bb=bottom;tf,tb=top
    v=[(x0,0,bf),(x1,0,bf),(x1,d,bb),(x0,d,bb),(x0,0,tf),(x1,0,tf),(x1,d,tb),(x0,d,tb)]
    return clean([[v[i] for i in face] for face in ((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))])


def rotate(v,rotation):
    x,y,z=v
    a,b,c=[math.radians(r) for r in rotation]
    x,y=x*math.cos(c)-y*math.sin(c),x*math.sin(c)+y*math.cos(c)
    x,z=x*math.cos(b)+z*math.sin(b),-x*math.sin(b)+z*math.cos(b)
    y,z=y*math.cos(a)-z*math.sin(a),y*math.sin(a)+z*math.cos(a)
    return (x,y,z)


def clip(solid,n,limit):
    """Keep n·point <= limit; close the resulting convex polyhedron."""
    faces=[];cut=[]
    for face in solid:
        output=[]
        for a,b in zip(face,face[1:]+face[:1]):
            da,db=dot(n,a)-limit,dot(n,b)-limit
            if da<=EPS:output.append(a)
            if (da>EPS and db<=EPS) or (da<=EPS and db>EPS):
                point=add(a,mul(sub(b,a),da/(da-db)))
                output.append(point);cut.append(point)
        if len(unique(output))>=3:faces.append(unique(output))
    cut=unique(cut)
    if len(cut)>=3:
        center=mean(cut);u=unit(sub(cut[0],center));v=cross(n,u)
        cut.sort(key=lambda p:math.atan2(dot(sub(p,center),v),dot(sub(p,center),u)))
        faces.append(cut)
    return clean(faces)


def solids(part):
    size=part['size'];w,d,h=size
    for values in (part['origin'],part.get('rotation',[0,0,0])):
        if len(values)!=3 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):raise ValueError('Invalid coordinates or rotation')
    if len(size)!=3 or any(not math.isfinite(v) or v<=0 for v in size):raise ValueError('Invalid part size')
    if part.get('outline') is not None:
        if part.get('profile') or part.get('seats'): raise ValueError('Outline cannot be combined with legacy profiles or seats')
        triangles=triangulate_outline(part['outline'])
        if any(y < -EPS or y>d+EPS or z < -EPS or z>h+EPS for triangle in triangles for y,z in triangle):
            raise ValueError('Outline exceeds its stock blank')
        pieces=[]
        for triangle in triangles:
            left=[(0,y,z) for y,z in triangle];right=[(w,y,z) for y,z in triangle]
            piece=clean([left,right]+[[left[i],left[(i+1)%3],right[(i+1)%3],right[i]] for i in range(3)])
            pieces.append(piece)
        center=add(part['origin'],mul(size,.5));half=mul(size,.5)
        return [[[add(center,rotate(sub(v,half),part.get('rotation',[0,0,0]))) for v in f] for f in piece] for piece in pieces]
    profile=part.get('profile');notch=profile.get('notch') if profile else None
    if profile and 'layers' in profile:
        if set(profile)!={'layers'} or part.get('seats'):raise ValueError('Layered profiles cannot combine with other cuts')
        layers=validate_layers(size,profile['layers']);pieces=[]
        for layer in layers:
            for outline in layer['outlines']:
                for triangle in triangulate_outline(outline):
                    left=[(layer['x'][0],y,z) for y,z in triangle]
                    right=[(layer['x'][1],y,z) for y,z in triangle]
                    pieces.append(clean([left,right]+[[left[i],left[(i+1)%3],right[(i+1)%3],right[i]] for i in range(3)]))
        center=add(part['origin'],mul(size,.5));half=mul(size,.5)
        return [[[add(center,rotate(sub(v,half),part.get('rotation',[0,0,0]))) for v in f] for f in piece] for piece in pieces]
    if profile and 'bands' in profile:
        if notch or part.get('seats'): raise ValueError('Banded profiles cannot combine with legacy notches/seats')
        bands=validate_bands(size,profile['bands'])
        pieces=[prism(*band['x'],d,band['bottom'],band['top']) for band in bands]
        center=add(part['origin'],mul(size,.5));half=mul(size,.5)
        return [[[add(center,rotate(sub(v,half),part.get('rotation',[0,0,0]))) for v in f] for f in piece] for piece in pieces]
    bottom,top=(profile['bottom'],profile['top']) if profile else ([0,0],[h,h])
    if len(bottom)!=2 or len(top)!=2 or any(not math.isfinite(v) for v in [*bottom,*top]):raise ValueError('Invalid profile')
    if any(t<b for b,t in zip(bottom,top)):raise ValueError('Inverted profile')
    pieces=[]
    if notch:
        depth=notch['depth'];seat=notch['top']
        if notch['side'] not in ('min','max') or not 0<depth<w or len(seat)!=2 or any(not math.isfinite(v) for v in seat) or any(not b<=s<=t for b,s,t in zip(bottom,seat,top)):raise ValueError('Invalid profile notch')
        if notch['side']=='min':pieces=[prism(0,depth,d,bottom,seat),prism(depth,w,d,bottom,top)]
        else:pieces=[prism(0,w-depth,d,bottom,top),prism(w-depth,w,d,bottom,seat)]
    else:pieces=[prism(0,w,d,bottom,top)]
    center=add(part['origin'],mul(size,.5));half=mul(size,.5)
    pieces=[[[add(center,rotate(sub(v,half),part.get('rotation',[0,0,0]))) for v in f] for f in piece] for piece in pieces if piece]
    for seat in part.get('seats',[]):
        lo,hi=seat['y'];z=seat['z']
        if not all(math.isfinite(v) for v in (lo,hi,z)) or lo>=hi:raise ValueError('Invalid seat')
        next_pieces=[]
        for piece in pieces:
            middle=clip(clip(piece,(0,-1,0),-lo),(0,1,0),hi)
            next_pieces += [clip(piece,(0,1,0),lo),clip(piece,(0,-1,0),-hi),clip(middle,(0,0,-1),-z)]
        pieces=[piece for piece in next_pieces if piece]
    if not pieces:raise ValueError('Part has no solid volume')
    return pieces


def vertices(solid): return unique([v for f in solid for v in f])
def bounds(pieces):
    vs=[v for s in pieces for f in s for v in f]
    return [(min(v[i] for v in vs),max(v[i] for v in vs)) for i in range(3)]


def directions(vectors):
    result=[]
    for v in vectors:
        n=unit(v)
        if norm(n)>EPS and not any(abs(dot(n,m))>1-1e-8 for m in result):result.append(n)
    return result


def penetration(a,b,tolerance=.001):
    """Separating axis test; returns minimum separating translation, or None."""
    va,vb=vertices(a),vertices(b)
    ea=directions(sub(f[(i+1)%len(f)],v) for f in a for i,v in enumerate(f))
    eb=directions(sub(f[(i+1)%len(f)],v) for f in b for i,v in enumerate(f))
    axes=directions([normal(f) for f in a+b]+[cross(u,v) for u in ea for v in eb])
    best=float('inf');direction=None
    for n in axes:
        pa=[dot(n,v) for v in va];pb=[dot(n,v) for v in vb]
        if min(max(pa),max(pb))-max(min(pa),min(pb))<=tolerance:return None
        distance=min(max(pa)-min(pb),max(pb)-min(pa))
        if distance<best:best,direction=distance,n
    return {'penetration_in':best,'axis':direction,'location':mean([mean(va),mean(vb)])}


def collision(a,b,tolerance=.001):
    ba,bb=bounds(a),bounds(b)
    if any(min(x[1],y[1])-max(x[0],y[0])<=tolerance for x,y in zip(ba,bb)):return None
    hits=[hit for u in a for v in b if (hit:=penetration(u,v,tolerance))]
    return max(hits,key=lambda h:h['penetration_in']) if hits else None


def polygon_area(poly):
    return abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(poly,poly[1:]+poly[:1])))/2 if len(poly)>2 else 0


def intersect2d(subject,boundary):
    if sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(boundary,boundary[1:]+boundary[:1]))<0:boundary=list(reversed(boundary))
    for a,b in zip(boundary,boundary[1:]+boundary[:1]):
        def side(p):return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
        output=[]
        for p,q in zip(subject,subject[1:]+subject[:1]):
            dp,dq=side(p),side(q)
            if dp>=-EPS:output.append(p)
            if (dp< -EPS and dq>=-EPS) or (dp>=-EPS and dq< -EPS):
                t=dp/(dp-dq);output.append(tuple(x+t*(y-x) for x,y in zip(p,q)))
        subject=output
        if not subject:break
    return subject


def contact_area(a,b,tolerance=.001,direction=None):
    """Actual opposed, coplanar face area; optional outward normal on A."""
    total=0;locations=[]
    if collision(a,b,tolerance):return 0,None
    for sa in a:
        for fa in sa:
            n=normal(fa)
            if direction is not None and dot(n,unit(direction))<1-1e-7:continue
            u=unit(sub(fa[1],fa[0]));v=cross(n,u)
            project=lambda point:(dot(point,u),dot(point,v))
            for sb in b:
                for fb in sb:
                    if dot(n,normal(fb))> -1+1e-7 or any(abs(dot(n,sub(p,fa[0])))>tolerance for p in fb):continue
                    area=polygon_area(intersect2d([project(p) for p in fa],[project(p) for p in fb]))
                    if area>EPS:total+=area;locations.append(mean(fa+fb))
    return total,mean(locations) if locations else None
