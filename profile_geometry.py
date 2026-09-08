"""Simple polygon profiles for cut lumber; no holes or curved edges."""
import math

EPS=1e-8


def triangulate_outline(outline):
    if not isinstance(outline,(list,tuple)) or not 3<=len(outline)<=128:
        raise ValueError('Outline needs 3–128 Y/Z points')
    points=[]
    for p in outline:
        if not isinstance(p,(list,tuple)) or len(p)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in p):
            raise ValueError('Outline points must be finite Y/Z pairs')
        points.append(tuple(p))
    def cross(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def on(a,b,c):
        return abs(cross(a,b,c))<=EPS and all(min(a[k],b[k])-EPS<=c[k]<=max(a[k],b[k])+EPS for k in (0,1))
    if len(set(points))!=len(points): raise ValueError('Outline contains repeated vertices')
    for i,(a,b) in enumerate(zip(points,points[1:]+points[:1])):
        for j,(c,d) in enumerate(zip(points,points[1:]+points[:1])):
            if j<=i or j==i+1 or (i==0 and j==len(points)-1): continue
            if (cross(a,b,c)*cross(a,b,d)<-EPS and cross(c,d,a)*cross(c,d,b)<-EPS) or any((on(a,b,c),on(a,b,d),on(c,d,a),on(c,d,b))):
                raise ValueError('Outline must not intersect itself')
    area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1]))/2
    if abs(area)<=EPS: raise ValueError('Outline has no area')
    if area<0: points.reverse()
    # Collinear points carry no geometry. Remove them before ear clipping.
    changed=True
    while changed and len(points)>3:
        changed=False
        for i,p in enumerate(points):
            if on(points[i-1],points[(i+1)%len(points)],p):
                points.pop(i);changed=True;break
    remaining=list(range(len(points)));triangles=[]
    while len(remaining)>3:
        for index,current in enumerate(remaining):
            prev=remaining[index-1];nxt=remaining[(index+1)%len(remaining)]
            a,b,c=points[prev],points[current],points[nxt]
            if cross(a,b,c)<=EPS: continue
            if any(all(v>=-EPS for v in (cross(a,b,points[k]),cross(b,c,points[k]),cross(c,a,points[k]))) for k in remaining if k not in (prev,current,nxt)):
                continue
            triangles.append((a,b,c));remaining.pop(index);break
        else: raise ValueError('Outline cannot be triangulated')
    triangles.append(tuple(points[i] for i in remaining))
    return triangles


def validate_bands(size, bands):
    """Connected X bands with linear Y/Z top/bottom cuts in one stock blank."""
    if not isinstance(bands,(list,tuple)) or not 1<=len(bands)<=32:
        raise ValueError('A banded profile needs 1–32 bands')
    w,d,h=size
    previous=None
    for band in bands:
        if not isinstance(band,dict) or set(band)!={'x','bottom','top'}:
            raise ValueError('Each profile band needs x, bottom and top pairs')
        if any(not isinstance(band[key],(list,tuple)) or len(band[key])!=2 for key in band):
            raise ValueError('Profile band coordinates must be pairs')
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for pair in band.values() for v in pair):
            raise ValueError('Profile band coordinates must be finite numbers')
        lo,hi=band['x'];bottom=band['bottom'];top=band['top']
        if lo<0 or hi>w+EPS or hi-lo<=EPS or any(a<0 or b>h+EPS or b-a<=EPS for a,b in zip(bottom,top)):
            raise ValueError('Profile band must have positive section within its stock blank')
        if previous:
            if abs(previous['x'][1]-lo)>EPS:
                raise ValueError('Profile bands must be contiguous and not overlap')
            if any(min(a,b)-max(c,d)<=EPS for a,b,c,d in zip(previous['top'],top,previous['bottom'],bottom)):
                raise ValueError('Adjacent bands must retain a connected section through the member')
            for key in ('top','bottom'):
                delta=[a-b for a,b in zip(previous[key],band[key])]
                if delta[0]*delta[1]<-EPS:
                    raise ValueError('Band edge profiles must not cross')
        previous=band
    return bands


def validate_layers(size, layers):
    """One connected blank cut to polygonal sections at successive depths."""
    import solid_geometry as geo
    if not isinstance(layers,(list,tuple)) or not 1<=len(layers)<=32:
        raise ValueError('Layered profile needs 1–32 layers')
    w,d,h=size;previous=0;nodes=[]
    for layer in layers:
        if not isinstance(layer,dict) or set(layer)!={'x','outlines'}:
            raise ValueError('Profile layer needs x and outlines')
        x=layer['x'];outlines=layer['outlines']
        if not isinstance(x,(list,tuple)) or len(x)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in x):
            raise ValueError('Layer depth must be a finite pair')
        if abs(x[0]-previous)>EPS or x[1]-x[0]<=EPS or x[1]>w+EPS:
            raise ValueError('Profile layers must partition the stock thickness')
        previous=x[1]
        if not isinstance(outlines,(list,tuple)) or not 1<=len(outlines)<=32:
            raise ValueError('Layer needs 1–32 polygon sections')
        for outline in outlines:
            triangles=triangulate_outline(outline)
            if any(y<-EPS or y>d+EPS or z<-EPS or z>h+EPS for tri in triangles for y,z in tri):
                raise ValueError('Layer outline exceeds its stock blank')
            nodes.append((x,outline,triangles))
    if abs(previous-w)>EPS:raise ValueError('Profile layers must cover the stock thickness')
    links=[set() for _ in nodes]
    for i,(x,p,triangles) in enumerate(nodes):
        for j,(other,q,other_triangles) in enumerate(nodes[:i]):
            same=abs(x[0]-other[0])<EPS and abs(x[1]-other[1])<EPS
            adjacent=abs(x[0]-other[1])<EPS or abs(other[0]-x[1])<EPS
            if not same and not adjacent:continue
            area=sum(geo.polygon_area(geo.intersect2d(a,b)) for a in triangles for b in other_triangles)
            if same and area>EPS:raise ValueError('Layer sections overlap')
            joined=adjacent and area>EPS
            if same:
                for a,b in zip(p,p[1:]+p[:1]):
                    for c,e in zip(q,q[1:]+q[:1]):
                        cross=lambda v:(b[0]-a[0])*(v[1]-a[1])-(b[1]-a[1])*(v[0]-a[0])
                        axis=0 if abs(b[0]-a[0])>abs(b[1]-a[1]) else 1
                        joined=joined or (abs(cross(c))<EPS and abs(cross(e))<EPS and min(max(a[axis],b[axis]),max(c[axis],e[axis]))-max(min(a[axis],b[axis]),min(c[axis],e[axis]))>EPS)
            if joined:links[i].add(j);links[j].add(i)
    seen={0};pending=[0]
    while pending:
        for other in links[pending.pop()]-seen:seen.add(other);pending.append(other)
    if len(seen)!=len(nodes):raise ValueError('Layered profile leaves disconnected pieces')
    return layers
