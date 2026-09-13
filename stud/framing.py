"""Reusable stock profiles and constrained fastener layouts, in project units."""
from dataclasses import dataclass
import math

import cadquery as cq

from .stock import cut_member
from .solids import round_member
from .cad import vector_at


def _clear_of_existing(model, new_ids, existing_ids, prefix):
    """Check possible interference across separately composed operations."""
    for pid in new_ids:
        a=model.shapes[pid]['world'].BoundingBox()
        for target in sorted(existing_ids):
            if pid==target:continue
            b=model.shapes[target]['world'].BoundingBox()
            if all(min(getattr(a,k+'max'),getattr(b,k+'max'))-max(getattr(a,k+'min'),getattr(b,k+'min'))>1e-8 for k in 'xyz'):
                model.requirement(prefix+'.'+pid+'.'+target,'collision',[pid,target],threshold=0)


@dataclass(frozen=True)
class MemberProfile:
    """Actual section and purchasing basis. An I profile is factory stock."""
    width: float
    depth: float
    product_id: str
    stock_lengths: tuple
    flange: float = 0
    web: float = 0
    unresolved: tuple = ()

    def __post_init__(self):
        values=(self.width,self.depth,*self.stock_lengths)
        if not self.product_id or not self.stock_lengths or not all(math.isfinite(v) and v>0 for v in values):
            raise ValueError('A member needs a product, positive section and available stock lengths.')
        if not all(math.isfinite(v) for v in (self.flange,self.web)):
            raise ValueError('Profile dimensions must be finite.')
        if (self.flange or self.web) and not (0<2*self.flange<self.depth and 0<self.web<self.width):
            raise ValueError('An I profile needs two flanges and a narrower web.')

    def cut(self,start,end):
        shape,location,blank=cut_member(start,end,(self.width,self.depth))
        if self.flange:
            side=(self.width-self.web)/2
            for x in (0,side+self.web):
                void=cq.Workplane('XY').box(side,blank['cut_length']+2,self.depth-2*self.flange,
                    centered=(False,False,False)).translate((x,-1,self.flange)).val()
                shape=shape.cut(void)
            blank['operations'].append(dict(kind='factory_profile',profile='I',flange=self.flange,web=self.web))
        return shape.clean(),location,blank


@dataclass(frozen=True)
class AnchorLayout:
    positions: tuple
    unresolved: tuple


def anchor_layout(length, *, max_spacing, end_distance, min_end, exclusions=(), min_count=2, min_spacing=0):
    """Place anchors within permitted end zones and around closed exclusions.

    Exclusions are forbidden *center* intervals, already expanded for the chosen
    hardware and neighboring parts. Impossible layouts return a specific gap,
    never a shortened list presented as a complete anchor pattern.
    """
    if not all(math.isfinite(v) and v>0 for v in (length,max_spacing,end_distance,min_end)):
        raise ValueError('Anchor dimensions must be finite and positive.')
    if min_end>end_distance or not isinstance(min_count,int) or min_count<1:
        raise ValueError('Invalid anchor end zone or minimum count.')
    if not math.isfinite(min_spacing) or not 0<=min_spacing<=max_spacing:
        raise ValueError('Minimum anchor spacing must fit within maximum spacing.')
    occupied=[]
    for a,b in exclusions:
        if not math.isfinite(a) or not math.isfinite(b) or a>b:raise ValueError('Invalid exclusion interval.')
        occupied.append((a,b))
    # Closed exclusions use a small scale-relative setback to avoid boundary contact.
    eps=max(1,length)*1e-8
    allowed=[(min_end,length-min_end)] if length>=2*min_end else []
    for a,b in sorted(occupied):
        next_allowed=[]
        for lo,hi in allowed:
            if b<lo or a>hi:next_allowed.append((lo,hi));continue
            if lo<a:next_allowed.append((lo,min(hi,a-eps)))
            if hi>b:next_allowed.append((max(lo,b+eps),hi))
        allowed=next_allowed
    first=[(lo,min(hi,end_distance)) for lo,hi in allowed if lo<=end_distance and lo<=hi]
    if not first:return AnchorLayout((),('No anchor fits the starting end zone.',))
    # Keep reachable intervals, rather than committing to a greedy anchor that
    # could strand the final end zone. Backtracking recovers a physical pattern.
    separation=max(min_spacing,eps*4)
    layers=[first];complete=False
    while True:
        current=layers[-1]
        finish=[hi for lo,hi in current if hi>=length-end_distance]
        if len(layers)>=min_count and finish:
            position=max(finish);complete=True;break
        reachable=[]
        for a,b in current:
            for lo,hi in allowed:
                left,right=max(lo,a+separation),min(hi,b+max_spacing)
                if left<=right:reachable.append((left,right))
        merged=[]
        for lo,hi in sorted(reachable):
            if merged and lo<=merged[-1][1]:merged[-1]=(merged[-1][0],max(merged[-1][1],hi))
            else:merged.append((lo,hi))
        if not merged or (not finish and max(hi for _,hi in merged)<=max(hi for _,hi in current)):
            position=max(hi for _,hi in current);break
        layers.append(merged)
    positions=[position]
    for previous in reversed(layers[:-1]):
        options=[min(hi,position-separation) for lo,hi in previous
                 if max(lo,position-max_spacing)<=min(hi,position-separation)+eps/10]
        position=max(options);positions.append(position)
    gaps=() if complete else ('No anchor pattern satisfies the supplied spacing, end zones, exclusions and minimum count.',)
    return AnchorLayout(tuple(reversed(positions)),gaps)


@dataclass(frozen=True)
class AnchorDetail:
    product_id: str
    diameter: float
    hole_diameter: float
    embedment: float
    projection: float
    washer_width: float
    washer_thickness: float
    nut_height: float
    unresolved: tuple

    def __post_init__(self):
        values=(self.diameter,self.hole_diameter,self.embedment,self.projection,
                self.washer_width,self.washer_thickness,self.nut_height)
        if not self.product_id or not all(math.isfinite(v) and v>0 for v in values):
            raise ValueError('Anchor detail dimensions must be finite and positive.')
        if not self.diameter<self.hole_diameter<self.washer_width or self.projection<self.washer_thickness+self.nut_height:
            raise ValueError('Anchor hole, washer and exposed shank must fit together.')

    def shape(self, *, sill_depth, hook_length=0, nut_diameter=None):
        """Envelope centered at XY zero, Z zero at the sill bottom."""
        if sill_depth<=0 or hook_length<0:raise ValueError('Anchor sill depth/hook length are invalid.')
        shaft=round_member((0,0,-self.embedment),(0,0,sill_depth+self.projection),self.diameter)
        if hook_length:shaft=shaft.fuse(round_member((0,0,-self.embedment),(hook_length,0,-self.embedment),self.diameter)).clean()
        washer=cq.Workplane('XY').box(self.washer_width,self.washer_width,self.washer_thickness,
            centered=(True,True,False)).translate((0,0,sill_depth)).val()
        washer=washer.cut(round_member((0,0,sill_depth-1),(0,0,sill_depth+self.washer_thickness+1),self.hole_diameter))
        nut=cq.Workplane('XY').polygon(6,nut_diameter or self.hole_diameter*1.5).extrude(self.nut_height).translate((0,0,sill_depth+self.washer_thickness)).val()
        return cq.Compound.makeCompound([shaft,washer,nut])


def anchored_sill(model, *, object_id, start, end, stock, anchor, support,
                  max_spacing, end_distance, min_end, avoid=(), exclusions=(), parent=None, kerf=None):
    """Cut a straight sill, place clear anchors, and retain incomplete layouts.

    `start/end` are top-center endpoints in the parent frame. `avoid` names
    already registered neighboring parts; their conservative stock-frame
    projections become exclusion intervals for hardware placement. Re-run after
    a neighbor changes. Product capacity and concrete detailing are caller inputs.
    """
    if stock.flange:raise ValueError('Sill stock must be solid.')
    if start[2]!=end[2]:raise ValueError('A sill must have a horizontal top in its parent frame.')
    if anchor.washer_width>=stock.width:raise ValueError('The washer must fit across the sill.')
    shape,loc,blank=stock.cut(start,end);world=model._parent_location(parent)*loc
    length=blank['cut_length'];radius=anchor.washer_width/2;occupied=list(exclusions)
    for pid in avoid:
        if pid not in model.shapes:raise ValueError(f'Unknown anchor obstacle: {pid}')
        bb=model.shapes[pid]['world'].moved(world.inverse).BoundingBox()
        if bb.xmax<stock.width/2-radius or bb.xmin>stock.width/2+radius:continue
        if bb.zmax<stock.depth or bb.zmin>stock.depth+anchor.projection:continue
        occupied.append((bb.ymin-radius,bb.ymax+radius))
    layout=anchor_layout(length,max_spacing=max_spacing,end_distance=end_distance,
        min_end=max(min_end,radius),exclusions=occupied,min_spacing=anchor.washer_width)
    before=set(model.requirements);before_connections=set(model.connections)
    existing=set(model.shapes)-{support}
    for y in layout.positions:
        shape=shape.cut(round_member((stock.width/2,y,-1),(stock.width/2,y,stock.depth+1),anchor.hole_diameter))
    blank['operations'].append(dict(kind='anchor_bores',diameter=anchor.hole_diameter,
                                   centers=[[stock.width/2,y] for y in layout.positions]))
    model.part(object_id,shape.clean(),location=loc,parent=parent,blank=blank,material=stock.product_id,label='Anchored sill')
    model.requirement(object_id+'.stock','stock_fit',[object_id]);model.requirement(object_id+'.valid','solid_valid',[object_id])
    model.requirement(object_id+'.seat','support',[object_id,support],
        threshold=stock.width*length-len(layout.positions)*math.pi*(anchor.hole_diameter/2)**2,
        direction=vector_at(world,(0,0,-1)))
    model.connection(object_id+'.bearing',parts=[object_id,support],description='Sill on its named supporting surface.',
        unresolved=['Confirm sill bearing, treatment, concrete edge distances and anchorage design.'])
    ids=[]
    for i,y in enumerate(layout.positions):
        x=stock.width/2;z=stock.depth
        envelope=anchor.shape(sill_depth=stock.depth).translate((x,y,0))
        pid=object_id+f'.anchor.{i}'
        model.part(pid,envelope,location=loc,parent=parent,
                   material=anchor.product_id,label='Anchor assembly envelope');ids.append(pid)
        model.requirement(pid+'.valid','solid_valid',[pid])
        for target in [object_id,*avoid]:model.requirement(pid+'.clear.'+target,'collision',[pid,target],threshold=0)
        model.connection(pid+'.tie',parts=[pid,object_id,support],description='Specified anchor envelope; threads and embedment mechanism are not modeled.',
                         unresolved=list(anchor.unresolved))
    if layout.unresolved:model.connection(object_id+'.layout_gap',parts=[object_id],description='Anchor layout could not meet the supplied constraints.',geometry_unresolved=True,unresolved=list(layout.unresolved))
    if len(ids)>1:model.requirement(object_id+'.anchors.clear','collision_free',ids,threshold=0)
    _clear_of_existing(model,[object_id,*ids],existing,object_id+'.interfaces')
    model.demand(object_id+'.stock_purchase',product_id=stock.product_id,specification={'section':[stock.width,stock.depth]},
        object_ids=[object_id],unit=model.units,purchase_unit='board',stock_lengths=list(stock.stock_lengths),
        cuts=[dict(object_id=object_id,length=length)],kerf=kerf if kerf is not None else (.125 if model.units=='in' else 3),unresolved=list(stock.unresolved))
    if ids:model.demand(object_id+'.anchors_purchase',product_id=anchor.product_id,specification=dict(
        diameter=anchor.diameter,embedment=anchor.embedment,projection=anchor.projection),object_ids=ids,
        quantity=len(ids),purchase_unit='each',unresolved=list(anchor.unresolved))
    model.expect(object_id+'.inventory',parts=[object_id,*ids],requirements=sorted(set(model.requirements)-before),
                 connections=sorted(set(model.connections)-before_connections))
    return dict(id=object_id,anchors=ids,layout=layout,top=start[2],blank=blank)
