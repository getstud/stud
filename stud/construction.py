"""General stock-frame cutting operations for native US construction."""
import math
import cadquery as cq

from .cad import point_at
from .contracts import StudError


def imperial_model(model):
    if model.units!='in':
        raise StudError('unit_mismatch','The built-in US construction components require an inch project. Metric projects use native millimeter geometry; they are not converted automatically.')


def cut_rafter(*, slope, run, seat=3.5, thickness=1.5, height=5.5):
    """Finished sloped solid in its stock frame, placement, and fabrication data."""
    if not 0 < slope <= 1 or not 0 < seat < run:
        raise ValueError('Use a positive slope up to 1:1 and a bearing seat inside the rafter run.')
    angle=math.atan(slope)
    length=(run+height*math.sin(angle))/math.cos(angle)
    rotation=cq.Location(cq.Vector(0,0,0),cq.Vector(1,0,0),math.degrees(angle))
    blank=cq.Workplane('XY').box(thickness,length,height,centered=(False,False,False)).val()
    stock_world=blank.moved(rotation)
    plumb_window=cq.Workplane('XY').box(thickness,run,run*slope+height/math.cos(angle),centered=(False,False,False)).val()
    rafter=stock_world.intersect(plumb_window)
    # Cut the seat in assembly coordinates, then archive the finished solid
    # in its actual rectangular stock frame for an independent fit query.
    notch=cq.Workplane('XY').box(thickness,seat,seat*slope,centered=(False,False,False))
    rafter=rafter.cut(notch.val()).moved(rotation.inverse)
    fabrication={'size':[thickness,length,height], 'cut_length':length,
                 'operations':[{'kind':'plumb_cut','slope':slope,'horizontal_run':run},
                               {'kind':'birdsmouth','seat':seat,'seat_z':seat*slope,'frame':'assembly',
                                'stock_seat_endpoints':[point_at(rotation.inverse,p) for p in [(0,0,seat*slope),(0,seat,seat*slope)]]}]}
    return rafter,rotation,fabrication
