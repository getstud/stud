"""Generic geometry and registration for cut construction stock."""
from dataclasses import dataclass
import math

import cadquery as cq


def _vector(value):
    try:values=tuple(value)
    except TypeError as error:raise ValueError('Expected three finite coordinates.') from error
    try:valid=len(values)==3 and all(math.isfinite(v) for v in values)
    except TypeError:valid=False
    if not valid:
        raise ValueError('Expected three finite coordinates.')
    return cq.Vector(*values)


@dataclass(frozen=True)
class Plane:
    """An oriented cutting plane; its positive side is removed."""
    point: tuple
    normal: tuple

    def __post_init__(self):
        point,normal=_vector(self.point),_vector(self.normal)
        if normal.Length<1e-12:raise ValueError('A plane needs a nonzero normal.')
        object.__setattr__(self,'point',point.toTuple())
        object.__setattr__(self,'normal',normal.normalized().toTuple())

    @classmethod
    def roof(cls, *, origin=(0,0,0),slope=(0,0)):
        """Create an upward plane from dz/dx and dz/dy slopes."""
        try:sx,sy=slope
        except (TypeError,ValueError) as error:raise ValueError('A roof slope needs two finite values.') from error
        return cls(tuple(origin),(-sx,-sy,1))

    def signed_distance(self,point):
        """Signed perpendicular distance; retained material is at or below zero."""
        return _vector(self.normal).dot(_vector(point)-_vector(self.point))

    def height_at(self,x,y):
        if not all(math.isfinite(v) for v in (x,y)):raise ValueError('Coordinates must be finite.')
        nx,ny,nz=self.normal
        if abs(nz)<1e-12:raise ValueError('A vertical plane has no unique roof elevation.')
        px,py,pz=self.point
        return pz-(nx*(x-px)+ny*(y-py))/nz

    def offset(self,distance):
        if not math.isfinite(distance):raise ValueError('Offset must be finite.')
        return Plane((_vector(self.point)+_vector(self.normal)*distance).toTuple(),self.normal)

    def intersection(self,other):
        if not isinstance(other,Plane):raise ValueError('Plane intersection needs another plane.')
        a,b=_vector(self.normal),_vector(other.normal);direction=a.cross(b)
        if direction.Length<1e-10:raise ValueError('Parallel planes have no unique intersection line.')
        da,db=a.dot(_vector(self.point)),b.dot(_vector(other.point))
        point=(b*da-a*db).cross(direction)/direction.dot(direction)
        return point.toTuple(),direction.normalized().toTuple()


def _below(shape,plane):
    normal,point=_vector(plane.normal),_vector(plane.point);box=shape.BoundingBox()
    corners=[cq.Vector(x,y,z) for x in (box.xmin,box.xmax) for y in (box.ymin,box.ymax) for z in (box.zmin,box.zmax)]
    if max(normal.dot(corner-point) for corner in corners)<=1e-10:return shape
    center=cq.Vector((box.xmin+box.xmax)/2,(box.ymin+box.ymax)/2,(box.zmin+box.zmax)/2)
    origin=center-normal*normal.dot(center-point)
    span=max(1,2*math.sqrt(box.xlen**2+box.ylen**2+box.zlen**2))
    keep=cq.Workplane(cq.Plane(origin=origin,normal=normal)).rect(span*2,span*2).extrude(-span).val()
    return shape.intersect(keep)


def cut_member(start,end,section, *, start_plane=None,end_plane=None,top_planes=(),up=(0,0,1)):
    """Cut rectangular stock between outward planes and optional backing planes."""
    start,end,up=_vector(start),_vector(end),_vector(up)
    try:width,depth=section
    except (TypeError,ValueError) as error:raise ValueError('Member stock needs a two-dimensional section.') from error
    if not all(math.isfinite(v) and v>0 for v in (width,depth)):
        raise ValueError('Member stock dimensions must be finite and positive.')
    axis=end-start
    if axis.Length<1e-10:raise ValueError('Member endpoints must differ.')
    axis=axis.normalized();across=axis.cross(up)
    if across.Length<1e-10:raise ValueError('Stock up direction must not be parallel to its length.')
    across=across.normalized();upper=across.cross(axis).normalized()
    horizontal=cq.Vector(axis.x,axis.y,0)
    if (start_plane is None or end_plane is None) and horizontal.Length<1e-10:
        raise ValueError('Vertical members need explicit end planes.')
    if start_plane is None:start_plane=Plane(start.toTuple(),(-horizontal).toTuple())
    if end_plane is None:end_plane=Plane(end.toTuple(),horizontal.toTuple())
    cuts=(start_plane,end_plane,*top_planes);extents=[]
    for index,plane in enumerate((start_plane,end_plane)):
        if not isinstance(plane,Plane):raise ValueError('Member cuts need oriented planes.')
        normal=_vector(plane.normal);denominator=normal.dot(axis)
        if (index==0 and denominator>=-1e-10) or (index==1 and denominator<=1e-10):
            raise ValueError('End-plane normals must point outward along the member axis.')
        values=[]
        for x in (-width/2,width/2):
            for z in (-depth,0):
                corner=start+across*x+upper*z
                values.append(normal.dot(_vector(plane.point)-corner)/denominator)
        extents.append(min(values) if index==0 else max(values))
    low,high=extents
    if high-low<=1e-10:raise ValueError('End planes leave no stock length.')
    origin=start+axis*low-across*(width/2)-upper*depth
    location=cq.Plane(origin=origin,xDir=across,normal=upper).location
    stock=cq.Workplane('XY').box(width,high-low,depth,centered=(False,False,False)).val()
    shape=stock.moved(location)
    for plane in cuts:
        if not isinstance(plane,Plane):raise ValueError('Member cuts need oriented planes.')
        shape=_below(shape,plane)
    if not shape.Solids() or shape.Volume()<=1e-10:raise ValueError('Cut planes remove the entire member.')
    local=shape.moved(location.inverse);local_planes=[]
    for plane in cuts:
        point=_vector(plane.point)-origin;normal=_vector(plane.normal)
        local_planes.append({'point':[point.dot(across),point.dot(axis),point.dot(upper)],
                             'normal':[normal.dot(across),normal.dot(axis),normal.dot(upper)]})
    blank={'size':[width,high-low,depth],'cut_length':high-low,
           'operations':[{'kind':'plane_cut','frame':'stock','planes':local_planes}]}
    return local,location,blank


class StockParts:
    """Register prismatic stock and emit purchase demands from its real blanks."""

    def __init__(self,model, *, parent=None,demand_prefix=''):
        self.model=model;self.parent=parent;self.demand_prefix=demand_prefix
        self._groups={}

    def add(self,object_id,result, *, section,product_id=None,label=None):
        try:shape,placement,blank=result
        except (TypeError,ValueError) as error:
            raise ValueError('Stock geometry must be a (solid, placement, blank) result.') from error
        try:width,depth=section
        except (TypeError,ValueError) as error:
            raise ValueError('Stock needs a two-dimensional section.') from error
        if not all(math.isfinite(value) and value>0 for value in (width,depth)):
            raise ValueError('Stock section dimensions must be finite and positive.')
        try:valid_blank=isinstance(blank,dict) and math.isfinite(blank.get('cut_length',float('nan'))) and blank['cut_length']>0
        except TypeError:valid_blank=False
        if not valid_blank:
            raise ValueError('Stock blank needs a finite positive cut length.')
        product_id=product_id or 'lumber.'+'x'.join(f'{value:g}' for value in (width,depth))
        group=self._groups.get(product_id)
        if group is not None and group['section']!=[width,depth]:
            raise ValueError('One stock product cannot describe different sections.')
        self.model.part(object_id,shape,parent=self.parent,label=label,location=placement,
                        material=product_id,blank=blank)
        self.model.requirement(object_id+'.blank','stock_fit',[object_id])
        if group is None:
            group=self._groups.setdefault(product_id,{'section':[width,depth],'parts':[],'cuts':[]})
        group['parts'].append(object_id)
        group['cuts'].append({'object_id':object_id,'length':blank['cut_length']})
        return object_id

    def purchase(self, *, stock_lengths,kerf=None,material='softwood',demand_id=None):
        lengths=list(stock_lengths)
        if not lengths or not all(math.isfinite(value) and value>0 for value in lengths):
            raise ValueError('Stock purchases need finite positive available lengths.')
        if kerf is None:kerf=.125 if self.model.units=='in' else 3
        if not math.isfinite(kerf) or kerf<0:
            raise ValueError('Stock kerf must be finite and nonnegative.')
        if demand_id is not None and len(self._groups)!=1:
            raise ValueError('An explicit demand id requires exactly one stock family.')
        ids=[]
        for product_id,group in sorted(self._groups.items()):
            key=demand_id or self.demand_prefix+product_id
            longest=max(cut['length'] for cut in group['cuts'])
            self.model.demand(key,product_id=product_id,
                specification={'material':material,'section':group['section']},
                object_ids=group['parts'],unit=self.model.units,purchase_unit='board',
                stock_lengths=lengths,cuts=group['cuts'],kerf=kerf,
                unresolved=[] if longest<=max(lengths)+.0004 else ['A member exceeds the supported stock lengths.'])
            ids.append(key)
        return ids


def cut_panel(frame, outline, thickness):
    """Cut a planar sheet profile in ``frame`` coordinates.

    The outline contains local X/Y points on the panel's base face. Thickness
    extends along the frame normal. The returned solid uses a normalized local
    blank frame, with its placement carrying the requested orientation.
    """
    if not isinstance(frame,cq.Plane):
        raise ValueError('A panel needs a CadQuery plane frame.')
    if not math.isfinite(thickness) or thickness<=0:
        raise ValueError('Panel thickness must be finite and positive.')
    try:points=[tuple(point) for point in outline]
    except TypeError as error:raise ValueError('A panel needs a two-dimensional profile.') from error
    try:valid_points=len(points)>=3 and all(len(point)==2 and all(math.isfinite(value) for value in point) for point in points)
    except TypeError:valid_points=False
    if not valid_points:
        raise ValueError('A panel needs at least three finite two-dimensional points.')
    minx,miny=min(point[0] for point in points),min(point[1] for point in points)
    maxx,maxy=max(point[0] for point in points),max(point[1] for point in points)
    if min(maxx-minx,maxy-miny)<=1e-10:
        raise ValueError('Panel profile must enclose an area.')
    profile=[(x-minx,y-miny) for x,y in points]
    try:shape=cq.Workplane('XY').polyline(profile).close().extrude(thickness).val()
    except Exception as error:raise ValueError('Panel profile must define one valid solid.') from error
    if not isinstance(shape,cq.Shape) or len(shape.Solids())!=1 or not shape.isValid() or shape.Volume()<=1e-10:
        raise ValueError('Panel profile must define one valid solid.')
    origin=frame.origin+frame.xDir*minx+frame.yDir*miny
    placement=cq.Plane(origin=origin,xDir=frame.xDir,normal=frame.zDir).location
    blank={'size':[maxx-minx,maxy-miny,thickness],'panel_axes':[0,1],
           'operations':[{'kind':'profile_cut','profile':[list(point) for point in profile]}]}
    return shape,placement,blank
