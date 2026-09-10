"""Explicit project units. Native geometry is never rescaled on publication."""
from .contracts import StudError

LENGTH_UNITS={'in':25.4,'mm':1.0}


def validate(units):
    if units not in LENGTH_UNITS:
        raise StudError('unsupported_units','Project modeling units must be in or mm.')
    return units


def convert(value, source, target):
    """Convert an explicitly dimensioned input or presentation boundary."""
    validate(source);validate(target)
    return value if source==target else value*LENGTH_UNITS[source]/LENGTH_UNITS[target]


def defaults(units):
    validate(units)
    return dict(linear_tolerance=.004 if units=='in' else .1,
                query_tolerance=.0004 if units=='in' else .01,angular_tolerance=.1)


def requirement_units(units, kind):
    validate(units)
    if kind=='solid_valid':return 'boolean'
    if kind in ('collision','collision_free','stock_fit'):return units+'3'
    if kind in ('support','contact'):return units+'2'
    return units
