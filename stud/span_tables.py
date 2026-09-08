"""Sourced rafter span selection. All spans and sections are actual inches.

This is an explicitly bounded table lookup, not a structural analysis engine.
"""
import math

SOURCE = 'https://www.southernpine.com/wp-content/uploads/2023/11/SPtable23_060113.pdf'
TABLE = 'SFPA Maximum Spans, 2013 edition, Table 23, Southern Pine No.2'
# Nominal size, actual section, maximum horizontal clear span at
# 12, 16, 19.2 and 24 inches on center. Feet/inches transcribed as inches.
_ROWS = (
    ('2x6', (1.5, 5.5), (132, 114, 104, 93)),
    ('2x8', (1.5, 7.25), (168, 145, 132, 118)),
    ('2x10', (1.5, 9.25), (199, 172, 157, 141)),
    ('2x12', (1.5, 11.25), (234, 203, 185, 165)),
)


def select_rafter_size(*, span, spacing, species, grade, roof_snow_psf,
                       dead_load_psf, deflection_limit, service,
                       top_edge_braced, uniform_load, load_basis):
    """Smallest listed section satisfying one verified SFPA table row.

    span is the horizontal distance between inside bearing faces, excluding
    overhang. Snow is adjusted roof snow load, not ground snow. Caller supplies
    the source establishing site loads and confirms the table's bracing and
    uniform-load assumptions. Other conditions require another sourced table.
    This lookup excludes notches, bearing capacity, overhangs, connections,
    uplift, ridge sizing and raised ties. It does not select a 2x4: Table 23
    starts at 2x6. No interpolation or substitution of species/loads occurs.
    """
    for name, value in (('span', span), ('spacing', spacing),
                        ('roof_snow_psf', roof_snow_psf), ('dead_load_psf', dead_load_psf),
                        ('deflection_limit', deflection_limit)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'{name} must be a finite positive number')
    if not isinstance(load_basis, str) or not load_basis.strip():
        raise ValueError('Provide the source/basis for the project roof loads')
    if (species != 'Southern Pine' or grade != 'No.2' or roof_snow_psf != 40
            or dead_load_psf != 15 or deflection_limit != 240 or service != 'dry'
            or top_edge_braced is not True or uniform_load is not True
            or spacing not in (12, 16, 19.2, 24)):
        raise ValueError('No matching bundled span table; consult an applicable published table for these conditions')
    column = (12, 16, 19.2, 24).index(spacing)
    for nominal, section, spans in _ROWS:
        if span <= spans[column]:
            return dict(nominal=nominal, section=section, required_span=span,
                        allowable_span=spans[column], spacing=spacing,
                        species=species, grade=grade, roof_snow_psf=roof_snow_psf,
                        dead_load_psf=dead_load_psf, deflection_limit=deflection_limit,
                        service=service, top_edge_braced=True, uniform_load=True,
                        load_basis=load_basis, table=TABLE, source=SOURCE,
                        scope='Rafter span-table lookup only; notch, bearing, overhang, uplift and connection checks are separate')
    raise ValueError('Span exceeds every bundled section; revise supports/spacing or use another designed system')
