"""Serialized demands, purchasing decisions and immutable Decimal estimates.

This module intentionally has no geometry dependency. A price-only change must
never need a CadQuery process, and old snapshots are read without recalculation.
"""
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from copy import deepcopy
import json
from pathlib import Path
import time

from .contracts import StudError, digest, encoded

CALCULATION_VERSION = 4
CENT = Decimal('0.01')
PRECEDENCE = {'estimated': 0, 'sourced': 1, 'manual': 2}


def decimal(value, *, nonnegative=True):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or (nonnegative and result < 0):
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError, TypeError) as error:
        raise StudError('invalid_quantity', f'Expected a finite {"nonnegative " if nonnegative else ""}decimal: {value}') from error


def money(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def ceil(value):
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def quote_key(record):
    return (record['product_id'], digest({'length_unit':'mm',**record['specification']}), record['purchase_unit'],
            str(decimal(record.get('pack_size', 1))))


def validate_quote(record):
    required = ('id', 'product_id', 'specification', 'purchase_unit', 'price', 'currency',
                'supplier', 'source', 'quote_date', 'save_sequence', 'kind')
    if any(key not in record for key in required):
        raise StudError('invalid_quote', f'Quote requires: {", ".join(required)}')
    if record['kind'] not in PRECEDENCE or decimal(record.get('pack_size', 1)) <= 0:
        raise StudError('invalid_quote', 'Quote kind and positive pack size are required.')
    if not isinstance(record['currency'], str) or len(record['currency']) != 3:
        raise StudError('invalid_quote', 'Use an explicit three-letter currency.')
    decimal(record['price'])
    quote_key(record)
    return record


def validate_clear(record):
    if any(k not in record for k in ('id','product_id','specification','purchase_unit','save_sequence')):
        raise StudError('invalid_quote','Clearing a quote requires its product, specification, unit and save identity.')
    if decimal(record.get('pack_size',1))<=0:
        raise StudError('invalid_quote','Clearing a quote requires a positive pack size.')
    quote_key(record)
    return record


def select_quotes(quotes, explicit=None):
    explicit = explicit or {}
    active = {}
    removals = {q['supersedes'] for q in quotes if q.get('supersedes')}
    clear_sequences = {}
    for record in quotes:
        if record.get('action') == 'clear_manual':
            validate_clear(record)
            key = quote_key(record)
            clear_sequences[key] = max(clear_sequences.get(key, -1), record['save_sequence'])
    by_id = {q['id']: q for q in quotes}
    for record in quotes:
        if record.get('action') == 'clear_manual' or record['id'] in removals:
            continue
        validate_quote(record)
        key = quote_key(record)
        if record['kind'] == 'manual' and record['save_sequence'] <= clear_sequences.get(key, -1):
            continue
        rank = (PRECEDENCE[record['kind']], record['save_sequence'])
        current = active.get(key)
        if current and rank == (PRECEDENCE[current['kind']], current['save_sequence']) and current['id'] != record['id']:
            raise StudError('quote_conflict', 'Two quotes have the same project save sequence; reconcile explicitly.',
                            references=[current['id'], record['id']])
        if not current or rank > (PRECEDENCE[current['kind']], current['save_sequence']):
            active[key] = record
    for product_id, quote_id in explicit.items():
        record = by_id.get(quote_id)
        if not record or record.get('action') or record['product_id'] != product_id:
            raise StudError('unresolved_quote', 'An explicitly selected quote is missing or incompatible.', references=[quote_id])
        validate_quote(record)
        active[quote_key(record)] = record
    selected = sorted(active.values(), key=lambda q: q['id'])
    basis = dict(policy='manual-over-sourced-over-estimated;latest-save-sequence', explicit_selection=explicit,
                 quotes=selected, calculation_version=CALCULATION_VERSION)
    return dict(id=digest(basis), **basis)


def plan_purchase(demand, inputs):
    missing = list(demand.get('unresolved', []))
    plan = dict(demand_id=demand['id'], product_id=demand['product_id'],
                object_ids=demand['object_ids'], specification=demand['specification'],
                purchase_unit=demand['purchase_unit'], pack_size=str(decimal(demand.get('pack_size', 1))),
                missing=missing, stock=[], basis='', demand_quantity=None)
    pack = decimal(demand.get('pack_size', 1))
    if pack <= 0:
        raise StudError('invalid_quantity', 'Pack size must be greater than zero.')
    cuts = demand.get('cuts')
    if cuts is not None:
        lengths = sorted(decimal(length) for length in (demand.get('stock_lengths') or []))
        kerf = decimal(demand.get('kerf', .125 if demand.get('length_unit')=='in' else 3))
        boards = []
        for cut in sorted(cuts, key=lambda cut: decimal(cut['length']), reverse=True):
            length = decimal(cut['length'])
            if length <= 0:
                raise StudError('invalid_quantity', 'Cut lengths must be positive.')
            eligible = [(board['remaining'], i) for i, board in enumerate(boards)
                        if board['remaining'] >= length + kerf]
            if eligible:
                board = boards[min(eligible)[1]]
                loss = kerf
            else:
                candidates = [stock for stock in lengths if stock >= length]
                if not candidates:
                    missing.append(f'No available blank fits {cut["object_id"]}: {length} {demand.get("length_unit","mm")}')
                    continue
                board = dict(length=min(candidates), remaining=min(candidates), cuts=[])
                boards.append(board)
                loss = Decimal(0)
            board['remaining'] -= length + loss
            board['cuts'].append(dict(**cut, kerf_before=str(loss)))
        plan['stock'] = [dict(id=f'{demand["id"]}.stock.{index + 1}', length=str(board['length']),
                              kerf=str(kerf),
                              trailing_kerf=str(min(kerf,board['remaining'])),
                              remaining=str(max(Decimal(0),board['remaining']-kerf)), cuts=board['cuts'])
                         for index, board in enumerate(boards)]
        quantity = Decimal(len(boards))
        plan['demand_quantity'] = str(sum((decimal(c['length']) for c in cuts), Decimal(0)))
        plan['basis'] = 'Specified blank lengths, longest cuts first, shortest fitting stock; kerf between cuts and before reusable offcuts.'
    elif demand.get('sheets') is not None:
        sheets = demand['sheets']
        quantity = Decimal(len(sheets))
        plan['stock'] = sheets
        plan['demand_quantity'] = str(len(sheets))
        plan['basis'] = 'Explicit authored sheet layouts; count actual identified sheets.'
    elif demand.get('quantity') is not None:
        raw = decimal(demand['quantity'])
        quantity = Decimal(ceil(raw / pack))
        plan['demand_quantity'] = str(raw)
        plan['basis'] = f'Physical demand {raw} {demand["unit"]}; {pack} per purchase unit.'
    else:
        quantity = None
        missing.append('Physical quantity or explicit stock plan is missing.')
    allowance = decimal(inputs.get('allowances', {}).get(demand['product_id'], 0))
    override = inputs.get('overrides', {}).get(demand['product_id'])
    plan['allowance'] = str(allowance)
    plan['quantity_override'] = str(decimal(override)) if override is not None else None
    if quantity is not None:
        quantity += allowance
    if override is not None:
        quantity = decimal(override)
        plan['basis'] += f' Explicit design purchase-quantity override: {quantity}.'
    plan['quantity'] = str(quantity) if quantity is not None else None
    return plan


def purchase_lines(demands, inputs):
    """Pool compatible demands before pack rounding; price concrete stock sizes.

    A quantity override applies once to a purchase line. Product-wide overrides
    are accepted only when that product has one purchasable specification.
    """
    groups={}
    for original in demands:
        demand=deepcopy(original)
        signature=digest({k:v for k,v in demand.items() if k not in
            ('id','object_ids','cuts','sheets','quantity','unresolved')})
        if signature not in groups:
            demand['demand_ids']=[demand['id']]
            groups[signature]=demand
        else:
            merged=groups[signature]
            merged['demand_ids'].append(demand['id'])
            merged['object_ids']+=demand['object_ids']
            merged.setdefault('unresolved',[]).extend(demand.get('unresolved',[]))
            for field in ('cuts','sheets'):
                if demand.get(field) is not None:merged[field]+=demand[field]
            if demand.get('quantity') is not None:merged['quantity']=str(decimal(merged['quantity'])+decimal(demand['quantity']))
    lines={}
    for demand in groups.values():
        plan=plan_purchase(demand,{})
        parts=[plan]
        if demand.get('cuts') is not None and plan['stock']:
            by_length={}
            for stock in plan['stock']:by_length.setdefault(stock['length'],[]).append(stock)
            parts=[]
            for length,stocks in sorted(by_length.items(),key=lambda row:decimal(row[0])):
                part=deepcopy(plan)
                part.update(specification={**plan['specification'],'stock_length':str(decimal(length).normalize())},
                    stock=stocks,quantity=str(len(stocks)),
                    demand_quantity=str(sum((decimal(cut['length']) for stock in stocks for cut in stock['cuts']),Decimal(0))),
                    object_ids=sorted({cut['object_id'] for stock in stocks for cut in stock['cuts']}))
                parts.append(part)
        for part in parts:
            key=quote_key(part)
            part['line_id']='purchase_'+digest(key)[:24]
            part['demand_ids']=sorted(demand['demand_ids'])
            if key not in lines:lines[key]=part
            else:
                previous=lines[key]
                previous['quantity']=str(decimal(previous['quantity'])+decimal(part['quantity'])) if previous['quantity'] is not None and part['quantity'] is not None else None
                previous['demand_quantity']=str(decimal(previous['demand_quantity'])+decimal(part['demand_quantity'])) if previous['demand_quantity'] is not None and part['demand_quantity'] is not None else None
                for field in ('object_ids','demand_ids','stock','missing'):previous[field]+=part[field]
    counts={}
    for line in lines.values():counts[line['product_id']]=counts.get(line['product_id'],0)+1
    for line in lines.values():
        for field in ('allowances','overrides'):
            values=inputs.get(field,{})
            if line['product_id'] in values and counts[line['product_id']]!=1:
                raise StudError('ambiguous_quantity_override','A product with multiple purchase sizes requires a purchase-line allowance or override.',references=[line['product_id'],line['line_id']])
        allowance=decimal(inputs.get('allowances',{}).get(line['line_id'],inputs.get('allowances',{}).get(line['product_id'],0)))
        override=inputs.get('overrides',{}).get(line['line_id'],inputs.get('overrides',{}).get(line['product_id']))
        line['allowance']=str(allowance)
        line['quantity_override']=str(decimal(override)) if override is not None else None
        if line['quantity'] is not None:line['quantity']=str(decimal(line['quantity'])+allowance)
        line['model_quantity']=line['quantity']
        if override is not None:
            line['quantity']=str(decimal(override))
            line['basis']+=f' Explicit purchase quantity: {line["quantity"]}.'
    return sorted(lines.values(),key=lambda row:row['line_id'])


def calculate(demands, inputs, quotes=None, *, basis=None, project_id=None, source_id=None, build_id=None, demand_findings=None):
    started = time.perf_counter()
    basis = basis or select_quotes(quotes or [], inputs.get('quote_selection'))
    selected = {quote_key(quote): quote for quote in basis['quotes']}
    currency = inputs.get('currency', 'USD')
    rows, missing = [], [dict(demand_id=finding.get('target'),reason=finding['message']) for finding in demand_findings or []]
    subtotal = Decimal(0)
    for plan in purchase_lines(demands, inputs):
        quote = selected.get(quote_key(plan))
        line_missing = plan['missing'][:]
        total = None
        if quote is None:
            line_missing.append('No applicable saved quote for this specification and purchase unit.')
        elif quote['currency'] != currency:
            line_missing.append(f'Quote currency {quote["currency"]} has no explicit conversion to {currency}.')
        elif plan['quantity'] is not None:
            total = decimal(plan['quantity']) * decimal(quote['price'])
            total = total.quantize(CENT, rounding=ROUND_HALF_UP)
            subtotal += total
        missing.extend(dict(demand_id=plan['demand_id'], line_id=plan['line_id'], reason=reason) for reason in line_missing)
        rows.append(dict(**{key: value for key, value in plan.items() if key != 'missing'},
                         quote=quote, unit_price=quote['price'] if quote else None,
                         line_total=money(total) if total is not None else None, missing=line_missing))
    if not demands:
        missing.append(dict(demand_id=None, reason='No material demands were declared.'))
    tax_rate = decimal(inputs.get('tax_rate', 0))
    contingency_rate = decimal(inputs.get('contingency_rate', 0))
    tax = (subtotal * tax_rate).quantize(CENT, rounding=ROUND_HALF_UP)
    contingency = ((subtotal + tax) * contingency_rate).quantize(CENT, rounding=ROUND_HALF_UP)
    result = dict(schema_version=1, calculation_version=CALCULATION_VERSION, project_id=project_id,
                  source_id=source_id, build_id=build_id, price_basis_id=basis['id'], price_basis=basis,
                  estimating_inputs=inputs, estimating_inputs_id=digest(inputs), currency=currency,
                  rounding='decimal ROUND_HALF_UP; each line and tax/contingency to 0.01',
                  rows=rows, known_subtotal=money(subtotal), tax=money(tax), contingency=money(contingency),
                  total=money(subtotal + tax + contingency) if not missing else None,
                  status='complete' if not missing else 'incomplete', missing=missing)
    result['id'] = digest(result)
    result['elapsed_seconds'] = time.perf_counter() - started
    return result


def quotes_from_directory(root):
    return [json.loads(path.read_bytes()) for path in sorted(Path(root).glob('records/quotes/*.json'))]


def compare(left, right, *, mode='historical'):
    if mode not in ('historical', 'common_price'):
        raise StudError('invalid_comparison', 'Choose historical or common_price comparison.')
    if mode == 'common_price' and left['price_basis_id'] != right['price_basis_id']:
        raise StudError('incompatible_price_basis', 'Common-price estimates must use exactly the same saved quotes.')
    def lines(estimate):
        # Old estimator snapshots can contain repeated product lines. Preserve
        # every original row instead of silently dropping all but the last.
        result={}
        for row in estimate.get('rows',[]):
            key=(*quote_key(row),row.get('line_id') or row.get('demand_id'))
            result[key]=row
        return result
    a, b = lines(left), lines(right)
    differences = []
    for key in sorted(set(a) | set(b)):
        old, new = a.get(key), b.get(key)
        changes = [name for name in ('demand_quantity', 'quantity', 'allowance', 'quantity_override', 'unit_price', 'line_total')
                   if (old or {}).get(name) != (new or {}).get(name)]
        differences.append(dict(product_id=key[0], left=old, right=new, changes=changes,
                                status='added' if old is None else 'removed' if new is None else 'changed' if changes else 'unchanged'))
    return dict(mode=mode, left_estimate_id=left.get('id'), right_estimate_id=right.get('id'),
                left_total=left.get('total'), right_total=right.get('total'),
                left_currency=left.get('currency','USD'),right_currency=right.get('currency','USD'),
                price_basis_id=left.get('price_basis_id') if mode == 'common_price' else None,
                assumptions_changed=left.get('estimating_inputs') != right.get('estimating_inputs'), lines=differences)
