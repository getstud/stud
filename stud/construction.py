"""General stock-frame cutting operations for native US construction."""
import math
import cadquery as cq

from .cad import point_at
from .contracts import StudError


def imperial_model(model):
    if model.units!='in':
        raise StudError('unit_mismatch','The built-in US construction components require an inch project. Metric projects use native millimeter geometry; they are not converted automatically.')


def cut_rafter(*, slope, run, seat=3.5, thickness=1.5, height=5.5, eave_overhang=0):
    """Finished sloped solid in its stock frame, placement, and fabrication data."""
    if not 0 < slope <= 1 or not 0 < seat < run:
        raise ValueError('Use a positive slope up to 1:1 and a bearing seat inside the rafter run.')
    if not all(math.isfinite(v) for v in (slope,run,seat,thickness,height,eave_overhang)) or min(thickness,height)<=0 or eave_overhang<0:
        raise ValueError('Rafter inputs must be finite, with positive stock and a nonnegative eave overhang.')
    from .stock import cut_member
    angle=math.atan(slope)
    top_rise=height/math.cos(angle)
    rafter,rotation,stock=cut_member(
        (thickness/2,-eave_overhang,-eave_overhang*slope+top_rise),
        (thickness/2,run,run*slope+top_rise),(thickness,height))
    length=stock['cut_length']
    rafter=rafter.moved(rotation)
    # Cut the seat in assembly coordinates, then archive the finished solid
    # in its actual rectangular stock frame for an independent fit query.
    notch=cq.Workplane('XY').box(thickness,seat,seat*slope,centered=(False,False,False))
    rafter=rafter.cut(notch.val()).moved(rotation.inverse)
    fabrication={'size':[thickness,length,height], 'cut_length':length,
                 'operations':[{'kind':'plumb_cut','slope':slope,'horizontal_run':run,'eave_overhang':eave_overhang},
                               {'kind':'birdsmouth','seat':seat,'seat_z':seat*slope,'frame':'assembly',
                                'stock_seat_endpoints':[point_at(rotation.inverse,p) for p in [(0,0,seat*slope),(0,seat,seat*slope)]]}]}
    return rafter,rotation,fabrication
