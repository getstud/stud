"""Roof-coordinate adapters over the generic construction-stock module."""
import math
import cadquery as cq

from .stock import Plane, cut_member


def _vector(value):
    try:values=tuple(value)
    except TypeError as error:raise ValueError('Expected three finite coordinates.') from error
    if len(values)!=3 or not all(math.isfinite(value) for value in values):
        raise ValueError('Expected three finite coordinates.')
    return cq.Vector(*values)


def cut_panel(plane,outline,thickness, *, x_direction=(1,0,0)):
    """Cut a planar panel from an XY footprint; plane is the panel underside.

    x_direction controls the original sheet's X/grain direction, projected onto
    the plane. The returned blank and polygon are in that sheet's own frame.
    """
    if len(outline)<3:raise ValueError('A panel needs a polygon footprint.')
    normal=_vector(plane.normal)
    if normal.z<=1e-10:raise ValueError('Roof panels require an upward, nonvertical plane.')
    x=_vector(x_direction);x=x-normal*x.dot(normal)
    if x.Length<1e-10:raise ValueError('Sheet X direction must lie along the roof plane.')
    x=x.normalized();y=normal.cross(x).normalized();origin=_vector(plane.point)
    points=[]
    for px,py in outline:
        vector=cq.Vector(px,py,plane.height_at(px,py))-origin
        points.append((vector.dot(x),vector.dot(y)))
    from .stock import cut_panel as cut_planar_panel
    return cut_planar_panel(cq.Plane(origin=origin,xDir=x,normal=normal),points,thickness)
