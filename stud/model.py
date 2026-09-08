"""Inch-based, agent-editable box model and conservative stock takeoff."""
from dataclasses import dataclass, asdict
from collections import defaultdict
import math
import json
from .environment import asset_path

@dataclass(frozen=True)
class Stock:
    id: str
    name: str
    color: str
    section: tuple | None = None
    lengths: tuple = ()
    sheet: tuple | None = None
    url: str = ''
    coverage_sq_ft: float | None = None
    purchase_unit: str = 'pack'
    waste_factor: float = 0
    category: str = 'Other'

class Project:
    def __init__(self, name):
        self.name, self.stocks, self.parts, self.dimensions = name, {}, [], []
        self.environment = []
        self.notes = []
        self.validation = {}
        self.allowances = []
        self.budget = {}
    def stock(self, id, name, color, **kw):
        if id in self.stocks: raise ValueError(f'Duplicate stock: {id}')
        candidate = Stock(id, name, color, **kw)
        for field in (candidate.section, candidate.lengths, candidate.sheet):
            if field and not all(math.isfinite(v) and v > 0 for v in field): raise ValueError('Stock dimensions must be positive and finite')
        if candidate.section and (len(candidate.section) != 2 or not candidate.lengths): raise ValueError('Lumber needs a two-dimensional section and stock lengths')
        if candidate.sheet and len(candidate.sheet) != 2: raise ValueError('Sheet needs two dimensions')
        if candidate.coverage_sq_ft is not None and (not math.isfinite(candidate.coverage_sq_ft) or candidate.coverage_sq_ft<=0 or not math.isfinite(candidate.waste_factor) or candidate.waste_factor<0): raise ValueError('Invalid coverage allowance')
        self.stocks[id] = candidate
    def box(self, id, assembly, stock, size, origin, *, rotation=(0,0,0), status='proposed', note=''):
        if any(p['id']==id for p in self.parts): raise ValueError(f'Duplicate part: {id}')
        if stock not in self.stocks: raise ValueError(f'Unknown stock: {stock}')
        for values in (size,origin,rotation):
            if len(values)!=3 or not all(math.isfinite(v) for v in values): raise ValueError('Expected three finite coordinates')
        if min(size)<=0: raise ValueError('Part dimensions must be positive')
        s=self.stocks[stock]
        cut_length = None
        if s.section:
            for axis in range(3):
                if sorted(size[j] for j in range(3) if j != axis) == sorted(s.section):
                    cut_length = size[axis]; break
            if cut_length is None: raise ValueError(f'{id}: dimensions do not match stock cross-section')
        if status not in ('proposed','verified'): raise ValueError('Unknown status')
        self.parts.append(dict(id=id,assembly=assembly,stock=stock,size=list(size),origin=list(origin),rotation=list(rotation),status=status,note=note,cut_length=cut_length))
    def profile_box(self, id, assembly, stock, width, depth, origin, bottom, top, *, blank_height=None, note=''):
        """Prism extruded along X; bottom/top are Z heights at front/back Y edges.
        Lumber takeoff counts the rectangular blank before the taper is cut.
        """
        values=(*bottom,*top)
        if len(bottom)!=2 or len(top)!=2 or not all(math.isfinite(v) for v in values): raise ValueError('Invalid profile')
        if min(bottom)!=0 or any(t<=b for t,b in zip(top,bottom)): raise ValueError('Profile must start at zero and have positive thickness')
        height=max(top)
        if blank_height is not None and blank_height<height: raise ValueError('Profile exceeds stock blank')
        self.box(id,assembly,stock,(width,depth,blank_height or height),origin,note=note)
        part=self.parts[-1];part['size'][2]=height
        part['profile']={'bottom':list(bottom),'top':list(top)}
        if blank_height is not None: part['blank_size']=[width,depth,blank_height]

    def context_asset(self, id, *, source, origin=(0, 0, 0), rotation=(0, 0, 0), parameters=None, name=None, visible=True):
        """Register visual environment geometry, excluded from parts and takeoffs.

        Modules export create({THREE, parameters, assetUrl}) and return Object3D.
        Local coordinates are inches, Z up; rotation is XYZ Euler degrees.
        """
        if not isinstance(id, str) or not id.strip() or any(a['id'] == id for a in self.environment):
            raise ValueError('Environment asset IDs must be nonempty and unique')
        for values in (origin, rotation):
            if len(values) != 3 or not all(math.isfinite(v) for v in values):
                raise ValueError('Expected three finite coordinates')
        if not isinstance(visible, bool) or (name is not None and not isinstance(name, str)):
            raise ValueError('Invalid environment name or visibility')
        parameters = {} if parameters is None else parameters
        if not isinstance(parameters, dict):
            raise ValueError('Environment parameters must be a JSON object')
        parameters = json.loads(json.dumps(parameters, allow_nan=False))
        self.environment.append(dict(id=id, name=name or id, source=asset_path(source),
            origin=list(origin), rotation=list(rotation), parameters=parameters, visible=visible))

    def dimension(self, label, start, end):
        if len(start) != 3 or len(end) != 3: raise ValueError('Dimensions need 3D coordinates')
        length=math.dist(start,end)
        if not math.isfinite(length) or length<=0: raise ValueError('Invalid dimension')
        self.dimensions.append(dict(label=label,start=start,end=end,inches=length))
    def export(self):
        if not self.parts: raise ValueError('Empty project')
        return dict(schema_version=1,name=self.name,units='in',axes='X width, Y depth, Z up',parts=self.parts,environment=self.environment,stocks={k:asdict(v) for k,v in self.stocks.items()},dimensions=self.dimensions,notes=self.notes,validation=self.validation,materials=takeoff(self.parts,self.stocks)+self.allowances,budget=self.budget)

def pack_lengths(cuts, lengths, kerf=.125):
    """First-fit decreasing. One kerf per cut, including final cut: conservative, not optimal."""
    bins=[]
    for part_id,length in sorted(cuts,key=lambda x:x[1],reverse=True):
        cost=length+kerf
        fit=next((b for b in bins if b['remaining']+1e-8>=cost or abs(b['remaining']-length)<1e-8),None)
        if fit is None:
            choices=[n for n in lengths if n+1e-8>=cost or abs(n-length)<1e-8]
            if not choices: raise ValueError(f'{part_id}: {length} in cut plus kerf exceeds available stock')
            n=min(choices); fit=dict(length=n,remaining=n,cuts=[]);bins.append(fit)
        if abs(fit['remaining']-length)<1e-8: cost=length
        fit['cuts'].append(dict(id=part_id,length=length));fit['remaining']=round(fit['remaining']-cost,6)
    return bins

def coverage_area(part):
    """Largest modeled face in square inches, independent of labels and rotation.

    Profile boxes are prisms extruded along local X. Account for their sloped
    top/bottom faces and trapezoidal sides rather than the bounding box.
    """
    width, depth, height = part['size']
    if 'profile' not in part:
        return math.prod(sorted(part['size'])[-2:])
    bottom = part['profile']['bottom']
    top = part['profile']['top']
    front, back = (top[i] - bottom[i] for i in range(2))
    return max(width * math.hypot(depth, top[1] - top[0]),
               width * math.hypot(depth, bottom[1] - bottom[0]),
               depth * (front + back) / 2,
               width * front, width * back)


def takeoff(parts,stocks):
    groups=defaultdict(list)
    for p in parts: groups[p['stock']].append(p)
    result=[]
    for sid,ps in groups.items():
        s=stocks[sid]; row=dict(stock=sid,name=s.name,parts=len(ps),url=s.url,category=s.category,status='proposed' if any(p['status']=='proposed' for p in ps) else 'verified')
        if s.coverage_sq_ft:
            area=sum(coverage_area(part) for part in ps)/144
            quantity=math.ceil(area*(1+s.waste_factor)/s.coverage_sq_ft)
            row.update(kind='coverage',square_ft=round(area,2),quantity=quantity,unit=s.purchase_unit,purchase=f'{quantity} × {s.purchase_unit}',basis=f'{area:.2f} sq ft largest-face area plus {s.waste_factor:.0%} cutting/waste allowance; {s.coverage_sq_ft:g} sq ft per purchase unit. Area allowance; final layout and accessories excluded.')
        elif s.section:
            cuts=[(p['id'],p['cut_length']) for p in ps]
            bins=pack_lengths(cuts,s.lengths)
            lengths=defaultdict(int)
            for b in bins: lengths[b['length']]+=1
            row.update(kind='lumber',linear_ft=round(sum(x[1] for x in cuts)/12,2),purchase='; '.join(f'{n} × {l/12:g} ft' for l,n in sorted(lengths.items())),bins=bins,basis='1/8 in kerf per cut; exact full-length use needs no cut. No defect allowance; not optimized.')
        elif s.sheet:
            area=sum(math.prod(sorted(p['size'])[-2:]) for p in ps)
            count=math.ceil(area/math.prod(s.sheet))
            row.update(kind='sheet',square_ft=round(area/144,2),purchase=f'{count} sheet(s) minimum by area',basis='Area lower bound only; no sheet nesting, offcut or grain-direction check. Not an order quantity.')
        else:
            row.update(kind='assembly',purchase='Specify system',basis='Concept geometry only; product and attachment details unresolved.')
        result.append(row)
    return result
