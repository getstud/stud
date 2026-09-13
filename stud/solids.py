"""Native-unit solids shared by formed, layered and round construction parts.

These operations make geometry only. Recipes own material systems, support
layouts, reinforcement, installation details and structural design evidence.
"""
import math

import cadquery as cq


def _positive(value, name):
    try:
        valid = math.isfinite(value) and value > 0
    except TypeError:
        valid = False
    if not valid:
        raise ValueError(f'{name} must be finite and positive.')


def _profile(points):
    try:
        points = [tuple(point) for point in points]
        valid = len(points) >= 3 and all(
            len(point) == 2 and all(math.isfinite(v) for v in point) for point in points)
    except TypeError:
        valid = False
    if not valid:
        raise ValueError('A profile needs at least three finite XY points.')
    return points


def prism(outline, depth, *, holes=(), frame=None):
    """Extrude a polygon with through openings along an oriented frame normal.

Outline and holes use frame-local XY. The result is in the caller's assembly
coordinates. Each hole must lie strictly inside the outline, apart from other
holes. Use ordinary CadQuery booleans for edge notches and intersecting cuts.
    """
    _positive(depth, 'Depth')
    if frame is None:
        frame = cq.Plane.XY()
    if not isinstance(frame, cq.Plane):
        raise ValueError('A prism frame must be a CadQuery plane.')

    def extrude(points):
        try:
            shape = cq.Workplane('XY').polyline(_profile(points)).close().extrude(depth).val()
            valid = len(shape.Solids()) == 1 and shape.isValid() and shape.Volume() > 0
        except Exception as error:
            raise ValueError('A profile must enclose one valid solid.') from error
        if not valid:
            raise ValueError('A profile must enclose one valid solid.')
        return shape

    outline = _profile(outline)
    shape = extrude(outline)
    boundaries = [cq.Workplane('XY').polyline(outline).close().wire().val()]
    for points in holes:
        points = _profile(points)
        hole = extrude(points)
        # A cut outside or across a boundary is usually a mistaken datum. Avoid
        # silently accepting it as a different opening or disconnected part.
        inner = cq.Workplane('XY').polyline(points).close().wire().val()
        if (hole.cut(shape).Volume() > hole.Volume() * 1e-9 or
                any(boundary.distance(inner) < 1e-7 for boundary in boundaries)):
            raise ValueError('Openings must lie strictly inside and apart from other openings.')
        shape = shape.cut(hole).clean()
        if len(shape.Solids()) != 1 or not shape.isValid():
            raise ValueError('Openings must leave one valid solid.')
        boundaries.append(inner)
    return shape.moved(frame.location)


def round_member(start, end, diameter, *, inner_diameter=0):
    """A solid round member or pipe between end-face centers, in native units.

Useful for piers, piles, straight reinforcement, dowels, anchors and drains.
Product details such as flutes, threads, bends or helixes remain recipe geometry.
    """
    _positive(diameter, 'Diameter')
    try:
        valid = math.isfinite(inner_diameter) and 0 <= inner_diameter < diameter
        points = [tuple(point) for point in (start, end)]
        valid = valid and all(len(point) == 3 and all(math.isfinite(v) for v in point) for point in points)
    except TypeError:
        valid = False
    if not valid:
        raise ValueError('Use finite endpoints and 0 <= inner diameter < outer diameter.')
    start, end = (cq.Vector(*point) for point in points)
    axis = end - start
    _positive(axis.Length, 'Member length')
    work = cq.Workplane(cq.Plane(origin=start, normal=axis)).circle(diameter / 2)
    if inner_diameter:
        work = work.circle(inner_diameter / 2)
    return work.extrude(axis.Length).val()
