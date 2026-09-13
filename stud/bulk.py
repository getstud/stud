"""Purchase bulk construction materials from their registered native volumes."""
from decimal import Decimal

from .contracts import StudError
from .estimate import decimal


def volume_demand(model, demand_id, *, product_id, specification, object_ids,
                  purchase_unit, purchase_increment=1, unresolved=None):
    """Measure final registered parts and buy volume in yd3, ft3 or m3.

Call after geometry edits. Boolean-union overlapping regions of one pour before
registration; separate pours may touch but must not overlap. Net modeled volume
is preserved independently of delivery rounding and estimating allowances.
    """
    lengths_mm = {'yd3': Decimal('914.4'), 'ft3': Decimal('304.8'), 'm3': Decimal('1000')}
    if purchase_unit not in lengths_mm:
        raise ValueError('Bulk purchase unit must be yd3, ft3 or m3.')
    increment = decimal(purchase_increment)
    if increment <= 0:
        raise StudError('invalid_quantity', 'Purchase increment must be positive.')
    ids = list(object_ids)
    if not ids or len(set(ids)) != len(ids):
        raise ValueError('A volume demand needs distinct physical part IDs.')
    volumes = []
    for part_id in ids:
        obj = model.objects.get(part_id)
        if obj is None or obj['material'] != product_id:
            raise ValueError('Every bulk part must exist and use the demand product.')
        volume = decimal(obj['volume'])
        if volume <= 0:
            raise ValueError('Bulk parts must have positive native volume.')
        volumes.append(volume)
    native_mm = Decimal('25.4') if model.units == 'in' else Decimal(1)
    pack = (lengths_mm[purchase_unit] / native_mm) ** 3
    return model.demand(demand_id, product_id=product_id, specification=specification,
                        object_ids=ids, quantity=str(sum(volumes)), unit=model.units + '3',
                        purchase_unit=purchase_unit, pack_size=str(pack),
                        purchase_increment=str(increment), unresolved=unresolved,
                        measurement='solid_volume',
                        quantity_basis='Registered net solid volumes; allowances are separate.')
