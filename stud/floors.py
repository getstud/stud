"""Floor regions assembled from stock, bearing interfaces and named openings.

Local X is the joist span, Y is the spacing axis, Z is up. Compose independently
placed rectangular regions for wings with different directions or elevations.
Python inputs remain the source of truth; no incremental dependency graph.
"""
from dataclasses import dataclass
import math

import cadquery as cq

from .cad import vector_at
from .framing import MemberProfile, _clear_of_existing
from .stock import StockParts, cut_panel


@dataclass(frozen=True)
class Bearing:
    """A named supporting part's transverse seat in a floor region's coordinates.

    The seat runs across the region in Y. Native checks verify the actual part,
    not just this declared interval. All supplied seat tops must share a datum.
    """
    part_id: str
    x: float
    width: float
    top: float

    def __post_init__(self):
        if not self.part_id or not all(math.isfinite(v) for v in (self.x,self.width,self.top)) or self.width<=0:
            raise ValueError('A bearing needs a named part, finite station/top and positive width.')


@dataclass(frozen=True)
class Opening:
    id: str
    x: float
    y: float
    length: float
    width: float

    def __post_init__(self):
        if not self.id or not all(math.isfinite(v) for v in (self.x,self.y,self.length,self.width)) or min(self.length,self.width)<=0:
            raise ValueError('An opening needs an id, finite position and positive clear dimensions.')


@dataclass(frozen=True)
class HangerDetail:
    """Explicit envelope dimensions; a product name alone does not prove capacity."""
    product_id: str
    seat: float
    height: float
    thickness: float
    unresolved: tuple

    def __post_init__(self):
        if not self.product_id or not all(math.isfinite(v) and v>0 for v in (self.seat,self.height,self.thickness)):
            raise ValueError('A hanger needs a product and positive envelope dimensions.')

    def shape(self,width,*,face_flange=0):
        """Envelope in member stock axes, with optional face-mount side flanges."""
        if width<=0 or face_flange<0:raise ValueError('Hanger width/flange are invalid.')
        t=self.thickness
        def box(x,y,z,a,b,c):return cq.Workplane('XY').box(a,b,c,centered=(False,False,False)).translate((x,y,z)).val()
        shape=box(-t,0,-t,width+2*t,self.seat,t)
        for x in (-t,width):shape=shape.fuse(box(x,0,0,t,self.seat,self.height))
        if face_flange:
            for x in (-face_flange-t,width+t):shape=shape.fuse(box(x,0,0,face_flange,t,self.height))
        return shape.clean()


@dataclass(frozen=True)
class PlannedMember:
    id: str
    role: str
    start: tuple
    end: tuple
    profile: MemberProfile
    supports: tuple


@dataclass(frozen=True)
class FloorLayout:
    length: float
    width: float
    bottom: float
    spacing: float
    rim: MemberProfile
    openings: tuple
    members: tuple
    unresolved: tuple = ()


def _free(lo,hi,occupied):
    cursor=lo
    for a,b in sorted(occupied):
        if b<=cursor or a>=hi:continue
        if a>cursor:yield cursor,min(a,hi)
        cursor=max(cursor,b)
    if cursor<hi:yield cursor,hi


def layout_floor(*, length, width, joist, rim, bearings, spacing, min_bearing,
                 openings=(), opening_stock=None, hanger=None):
    """Pure layout: regenerate all dependent members from shared inputs.

    Openings must fit between transverse bearing lines. An opening that cuts a
    support requires a different support design, rather than a silently cut beam.
    No species, grade, loading, product or fastening choices are inferred here.
    """
    if not isinstance(joist,MemberProfile) or not isinstance(rim,MemberProfile):raise ValueError('Supply joist and rim stock profiles.')
    if rim.flange:raise ValueError('Perimeter rim stock must be solid.')
    if not all(math.isfinite(v) and v>0 for v in (length,width,spacing,min_bearing)) or spacing<=joist.width:
        raise ValueError('Positive floor dimensions, bearing length and non-overlapping spacing are required.')
    if joist.depth!=rim.depth:raise ValueError('Joist and rim depths must match.')
    if min(length,width)<=2*rim.width+joist.width:raise ValueError('Floor is too small for the selected members.')
    bearings=tuple(sorted(bearings,key=lambda b:b.x));openings=tuple(openings)
    if not bearings or len({b.part_id for b in bearings})!=len(bearings):raise ValueError('Supply uniquely named bearing interfaces.')
    if any(abs(b.top-bearings[0].top)>1e-8 for b in bearings):raise ValueError('Bearing tops must share a datum within each floor region.')
    if any(a.x+a.width/2>=b.x-b.width/2 for a,b in zip(bearings,bearings[1:])):raise ValueError('Bearing intervals must be separate and ordered.')
    if any(b.x+b.width/2<0 or b.x-b.width/2>length for b in bearings):raise ValueError('Bearing lies outside this region.')
    if len({o.id for o in openings})!=len(openings):raise ValueError('Opening ids must be unique.')
    if openings and (not isinstance(opening_stock,MemberProfile) or opening_stock.flange or opening_stock.depth!=joist.depth):
        raise ValueError('Openings require explicit matching-depth solid header/trimmer stock.')
    t=rim.width;bottom=bearings[0].top;top=bottom+joist.depth
    interior=[b.x for b in bearings if b.x-b.width/2>t and b.x+b.width/2<length-t]
    stations=[t]+interior+[length-t]
    members=[];trims=[];header_faces=[];corner_rows=[];opening_extents=[]
    def bearing_at(x,inward):
        for b in bearings:
            lo,hi=b.x-b.width/2,b.x+b.width/2
            a,c=sorted((x,x+inward*min_bearing))
            if lo<=a+1e-8 and hi>=c-1e-8:return ('bearing',b.part_id)
        return ('missing',f'No {min_bearing:g}-unit bearing at X={x:g}.')
    def span(key,role,x0,x1,y,profile,ends=None):
        if x1-x0<=1e-8:return
        ends=ends or (bearing_at(x0,1),bearing_at(x1,-1))
        members.append(PlannedMember(key,role,(x0,y,top),(x1,y,top),profile,ends))
    # Rim pieces occupy disjoint corners, preserving their original stock frames.
    for key,x in [('west',t/2),('east',length-t/2)]:
        members.append(PlannedMember('rim.'+key,'rim',(x,0,top),(x,width,top),rim,()))
    for key,y in [('south',t/2),('north',width-t/2)]:span('rim.'+key,'rim',t,length-t,y,rim,())
    for o in openings:
        h=opening_stock.width
        if o.x-h<=t or o.x+o.length+h>=length-t or o.y-h<=t or o.y+o.width+h>=width-t:
            raise ValueError(f'Opening {o.id} and its framing must fit inside the rim.')
        for other in openings:
            if other is not o and o.x-h<other.x+other.length+h and o.x+o.length+h>other.x-h and o.y-h<other.y+other.width+h and o.y+o.width+h>other.y-h:
                raise ValueError('Opening framing overlaps; compose a shared opening or separate regions.')
        if any(o.x-h<b.x+b.width/2 and o.x+o.length+h>b.x-b.width/2 for b in bearings):
            raise ValueError(f'Opening {o.id} cuts a bearing line; revise the support design.')
        left=max(x for x in stations if x<o.x-h);right=min(x for x in stations if x>o.x+o.length+h)
        if any(left<b and right>a and o.y-h<hi and o.y+o.width+h>lo for a,b,lo,hi in opening_extents):
            raise ValueError('Opening framing extents overlap; combine the openings or supply shared framing.')
        opening_extents.append((left,right,o.y-h,o.y+o.width+h))
        if hanger:
            setback=hanger.seat+2*hanger.thickness+joist.width/2
            if o.width<2*setback+joist.width:raise ValueError('Opening is too narrow for the selected corner hanger envelopes.')
            corner_rows.extend([(o.id+'.south',left,right,o.y+setback,o.y,o.y+setback),
                                (o.id+'.north',left,right,o.y+o.width-setback,o.y+o.width-setback,o.y+o.width)])
        for side,y in [('south',o.y-h/2),('north',o.y+o.width+h/2)]:
            key=f'opening.{o.id}.trimmer.{side}'
            span(key,'trimmer',left,right,y,opening_stock)
            trims.append((key,left,right,y-h/2,y+h/2))
        for side,x in [('west',o.x-h/2),('east',o.x+o.length+h/2)]:
            key=f'opening.{o.id}.header.{side}'
            members.append(PlannedMember(key,'header',(x,o.y,top),(x,o.y+o.width,top),opening_stock,
                (('hanger',f'opening.{o.id}.trimmer.south'),('hanger',f'opening.{o.id}.trimmer.north'))))
            header_faces.append((x-h/2,x+h/2,o.y,o.y+o.width,key))
    grid=[];first=t+joist.width/2;last=width-t-joist.width/2
    for i in range(math.floor((last-first)/spacing)+1):grid.append((f'grid.{i}',first+i*spacing))
    if last-grid[-1][1]>=joist.width-1e-8:grid.append(('edge.north',last))
    def field(key,y,left=t,right=None):
        right=length-t if right is None else right
        occupied=[(a,b) for _,a,b,lo,hi in trims if y-joist.width/2<hi-1e-8 and y+joist.width/2>lo+1e-8]
        for _,a,b,row,lo,hi in corner_rows:
            if abs(y-row)>1e-8 and (lo-joist.width/2<y<hi+joist.width/2 or abs(y-row)<joist.width+2*hanger.thickness):
                occupied.append((a,b))
        for o in openings:
            h=opening_stock.width
            if y+joist.width/2>o.y and y-joist.width/2<o.y+o.width:occupied.append((o.x-h,o.x+o.length+h))
        for a,b in _free(left,right,occupied):
            cuts=[a]+[x for x in interior if a<x<b]+[b]
            for x0,x1 in zip(cuts,cuts[1:]):
                ends=[bearing_at(x0,1),bearing_at(x1,-1)]
                for k,x in enumerate((x0,x1)):
                    for lo,hi,ya,yb,host in header_faces:
                        if ya<=y-joist.width/2+1e-8 and y+joist.width/2<=yb+1e-8 and abs(x-(hi if k==0 else lo))<1e-8:
                            ends[k]=('hanger',host)
                # Endpoint names tie segmentation to supports/openings, not list order.
                suffix='.'.join(kind+'_'+target for kind,target in ends)
                span('joist.'+key+'.'+suffix,'joist',x0,x1,y,joist,tuple(ends))
    for key,y in grid:field(key,y)
    for key,a,b,y,_,_ in corner_rows:field('opening_edge.'+key,y,a,b)
    # A trimmer replaces only its span; infill prevents an excessive adjacent gap.
    for key,a,b,lo,hi in trims:
        center=(lo+hi)/2
        for side,ys in [('south',[y for _,y in grid if y+joist.width/2<=lo]),
                        ('north',[y for _,y in grid if y-joist.width/2>=hi])]:
            if not ys:continue
            neighbor=max(ys) if side=='south' else min(ys)
            if abs(center-neighbor)>spacing+1e-8:field('infill.'+key+'.'+side,(center+neighbor)/2,a,b)
    # Verify the resulting rows, including rows suppressed near hanger envelopes.
    # Check each longitudinal interval independently; stair voids are intentional.
    cuts=sorted({v for member in members for v in (member.start[0],member.end[0])})
    gaps=[]
    for left,right in zip(cuts,cuts[1:]):
        x=(left+right)/2
        rows=sorted({member.start[1] for member in members
                     if member.start[1]==member.end[1] and member.start[0]<=x<=member.end[0]})
        voids=[(o.y-opening_stock.width/2,o.y+o.width+opening_stock.width/2) for o in openings
               if o.x-opening_stock.width<=x<=o.x+o.length+opening_stock.width]
        for lo,hi in zip(rows,rows[1:]):
            for a,b in _free(lo,hi,voids):
                if b-a>spacing+1e-7:
                    gaps.append(f'Joist row spacing {b-a:g} exceeds {spacing:g} between Y={a:g} and {b:g}, across X={left:g} to {right:g}; revise the opening/hanger layout or add resolved infill.')
    return FloorLayout(length,width,bottom,spacing,rim,openings,tuple(members),tuple(gaps))


def _purchases(model,stock,profiles,prefix,kerf):
    # StockParts groups equal products and retains physical cut lengths.
    for product,group in stock._groups.items():
        profile=profiles[product]
        model.demand(prefix+'.purchase.'+product,product_id=product,specification=dict(
            section=[profile.width,profile.depth],profile='I' if profile.flange else 'solid',
            flange=profile.flange,web=profile.web),object_ids=group['parts'],unit=model.units,
            purchase_unit='board',stock_lengths=list(profile.stock_lengths),cuts=group['cuts'],kerf=kerf,
            unresolved=list(profile.unresolved))


def _hanger(model,pid,host,end,detail,parent):
    entry=model.shapes[pid];blank=model.objects[pid]['blank'];w,L,d=blank['size'];t=detail.thickness
    if detail.height>d or detail.seat>L:raise ValueError('Hanger envelope exceeds its supported member.')
    # In stock coordinates X is across the member and Y follows its length.
    shape=detail.shape(w)
    if end:shape=shape.rotate((w/2,L/2,0),(w/2,L/2,1),180)
    hid=f'{pid}.end{end}.hanger'
    # The returned member frame already includes all parent placement.
    model.part(hid,shape.clean(),parent=parent,location=model._parent_location(parent).inverse*entry['location'],
               material=detail.product_id,label='Hanger envelope')
    model.requirement(hid+'.seat','support',[pid,hid],threshold=w*detail.seat,
                      direction=vector_at(entry['location'],(0,0,-1)))
    model.requirement(hid+'.clear','collision',[pid,hid],threshold=0)
    model.requirement(hid+'.host','contact',[hid,host],threshold=2*t*detail.height)
    model.requirement(hid+'.valid','solid_valid',[hid])
    model.connection(hid+'.tie',parts=[pid,hid,host],description='Selected end-hanger detail.',
                     unresolved=list(detail.unresolved))
    return hid


def frame_floor(model, *, object_id, length, width, joist, rim, bearings, spacing,
                min_bearing, openings=(), opening_stock=None, hanger=None, location=None,
                parent=None, kerf=None, unresolved=()):
    """Register a complete framing region; never installs decking implicitly."""
    bearings=tuple(bearings)
    layout=layout_floor(length=length,width=width,joist=joist,rim=rim,bearings=bearings,
        spacing=spacing,min_bearing=min_bearing,openings=openings,opening_stock=opening_stock,hanger=hanger)
    profiles={}
    for member in layout.members:
        profile=member.profile
        if profile.product_id in profiles and profiles[profile.product_id]!=profile:
            raise ValueError('One product cannot have conflicting profile or purchase specifications.')
        profiles[profile.product_id]=profile
    before=set(model.requirements);before_connections=set(model.connections)
    existing=set(model.shapes)
    model.assembly(object_id,'Floor framing',location=location,parent=parent)
    stock=StockParts(model,parent=object_id);ids=[];hangers=[];mapping={}
    with model.batch():
        for member in layout.members:
            pid=object_id+'.'+member.id;mapping[member.id]=pid
            stock.add(pid,member.profile.cut(member.start,member.end),section=(member.profile.width,member.profile.depth),
                      product_id=member.profile.product_id,label=member.role)
            model.requirement(pid+'.valid','solid_valid',[pid]);ids.append(pid)
    for member in layout.members:
        pid=mapping[member.id];blank=model.objects[pid]['blank'];w,L,d=blank['size']
        if member.role=='rim' and not member.supports:
            x=member.start[0]
            seat=next((b for b in bearings if b.x-b.width/2<=x-w/2+1e-8 and b.x+b.width/2>=x+w/2-1e-8),None)
            if seat:
                model.requirement(pid+'.bearing','support',[pid,seat.part_id],threshold=w*L,
                    direction=vector_at(model.shapes[pid]['location'],(0,0,-1)))
            else:
                model.connection(pid+'.missing',parts=[pid],description='Perimeter bearing needs resolution.',
                    geometry_unresolved=True,unresolved=['Provide a bearing interface under this rim.'])
        for k,(kind,target) in enumerate(member.supports):
            if kind=='bearing':
                lo=0 if k==0 else L-min_bearing
                model.requirement(pid+f'.end{k}.bearing','support',[pid,target],threshold=w*min_bearing,
                    direction=vector_at(model.shapes[pid]['location'],(0,0,-1)),
                    region_local=dict(min=[0,lo,0],max=[w,lo+min_bearing,d]))
                model.connection(pid+f'.end{k}.tie',parts=[pid,target],description='Direct end bearing.',
                    unresolved=['Specify fastening, end restraint and any required bearing stiffeners.'])
            elif kind=='hanger' and hanger:
                hangers.append(_hanger(model,pid,mapping[target],k,hanger,object_id))
            else:
                host=mapping.get(target)
                model.connection(pid+f'.end{k}.missing',parts=[pid]+([host] if host else []),
                    description='End support needs resolution.',geometry_unresolved=True,
                    unresolved=[target if kind=='missing' else 'Select a hanger detail for this end.'])
    _purchases(model,stock,profiles,object_id,kerf if kerf is not None else (.125 if model.units=='in' else 3))
    if hangers:
        model.demand(object_id+'.hangers',product_id=hanger.product_id,specification=dict(seat=hanger.seat,
            height=hanger.height,thickness=hanger.thickness),object_ids=hangers,quantity=len(hangers),
            unit='each',purchase_unit='each',unresolved=list(hanger.unresolved))
    model.requirement(object_id+'.members.clear','collision_free',ids,threshold=0)
    # Include all interfaces without testing deliberate hanger/host attachment as bearing.
    if hangers:model.requirement(object_id+'.hardware.clear','collision_free',ids+hangers,threshold=0)
    _clear_of_existing(model,ids+hangers,existing,object_id+'.interfaces')
    if layout.unresolved:
        model.connection(object_id+'.spacing',parts=ids,description='Resulting joist spacing needs resolution.',
            geometry_unresolved=True,unresolved=list(layout.unresolved))
    model.connection(object_id+'.design',parts=ids,description='Floor system design basis.',unresolved=list(unresolved))
    model.connection(object_id+'.erection',parts=ids,description='Framing assembly restraint.',
        unresolved=['Specify product-specific bearing blocking, temporary erection restraint and installation sequence.'])
    model.expect(object_id+'.inventory',parts=ids+hangers,requirements=sorted(set(model.requirements)-before),
                 connections=sorted(set(model.connections)-before_connections))
    world=model._parent_location(object_id)
    model.drawing(object_id+'.plan',label='Floor framing',objects=ids+hangers,
        direction=vector_at(world,(0,0,1)),up=vector_at(world,(0,1,0)))
    model.step(object_id+'.frame','Install the specified framing and connections; review outstanding support and restraint details.',
        parts=ids+hangers,view=object_id+'.plan')
    return dict(id=object_id,layout=layout,parts=ids,hangers=hangers,members=mapping,
                bottom=layout.bottom,top=layout.bottom+joist.depth,location=world)


def _legacy_deck_floor(model,floor, *, product_id, thickness, sheet_size, gap, seam_exclusions=(), unresolved=(), kerf=None):
    """Add supported sheet cuts from the same floor/opening definition.

    Sheet-size axes follow the floor's X/Y axes. Only this operation adds sheet
    material and seam backing; it does not rewrite the framing or its openings.
    """
    from .buildings import panel_spans
    sx,sy=sheet_size;layout=floor['layout'];t=layout.rim.width
    if not product_id or not all(math.isfinite(v) and v>0 for v in (sx,sy,thickness)) or not math.isfinite(gap) or not 0<=gap<t:
        raise ValueError('Supply positive sheet dimensions and a nonnegative joint gap narrower than its backing.')
    seam_exclusions=tuple(seam_exclusions)
    if any(not all(math.isfinite(v) for v in (a,b)) or a>b for a,b in seam_exclusions):
        raise ValueError('Seam exclusions need finite ordered X intervals.')
    boxes=[]
    for m in layout.members:
        x0,y0,_=m.start;x1,y1,_=m.end;w=m.profile.width
        boxes.append((min(x0,x1)-(w/2 if x0==x1 else 0),max(x0,x1)+(w/2 if x0==x1 else 0),
                      min(y0,y1)-(w/2 if y0==y1 else 0),max(y0,y1)+(w/2 if y0==y1 else 0)))
    candidates=sorted({m.start[1] for m in layout.members if m.start[1]==m.end[1]})
    backed=[]
    for y in candidates:
        occupied=[(a,b) for a,b,c,d in boxes if c<=y<=d]
        occupied += [(o.x,o.x+o.length) for o in layout.openings if o.y<=y<=o.y+o.width]
        if not list(_free(0,layout.length,occupied)):backed.append(y)
    rows=panel_spans(layout.width,sy,backed)
    # Keep each seam's entire backing width on one side of a member endpoint.
    # A row ending at a beam cannot back the sheet on the other side of it.
    columns=[];x=0
    boundaries=sorted({v for a,b,_,_ in boxes for v in (a,b)},reverse=True)
    while x<layout.length:
        end=min(x+sx,layout.length)
        if end<layout.length:
            while True:
                previous=end
                for boundary in boundaries:
                    if end-t/2<boundary<end+t/2:end=boundary-t/2
                for lo,hi in sorted(seam_exclusions,reverse=True):
                    if end+t/2>lo and end-t/2<hi:end=lo-t/2-max(layout.length,layout.width)*1e-7
                if end==previous:break
        if end-x<=gap:raise ValueError('Sheet size cannot accommodate backing at these member endpoints.')
        columns.append((x,end));x=end
    object_id=floor['id']+'.deck';model.assembly(object_id,'Floor decking',parent=floor['id'])
    before=set(model.requirements);before_connections=set(model.connections)
    existing=set(model.shapes)-set(floor['parts'])
    stock=StockParts(model,parent=object_id);blocks=[];panels=[];sheets=[]
    with model.batch():
        for col,(x,_) in enumerate(columns[1:],1):
            occupied=[(c,d) for a,b,c,d in boxes if a<x+t/2 and b>x-t/2]
            occupied += [(o.y,o.y+o.width) for o in layout.openings if o.x<x+t/2 and o.x+o.length>x-t/2]
            for i,(a,b) in enumerate(_free(0,layout.width,occupied)):
                pid=object_id+f'.backing.{col}.{i}'
                stock.add(pid,layout.rim.cut((x,a,floor['top']),(x,b,floor['top'])),
                          section=(t,layout.rim.depth),product_id=layout.rim.product_id,label='Sheet seam backing')
                model.requirement(pid+'.valid','solid_valid',[pid]);blocks.append(pid)
        for col,(x,lastx) in enumerate(columns):
            for row,(y,lasty) in enumerate(rows):
                w=lastx-x-(gap if lastx<layout.length else 0);h=lasty-y-(gap if lasty<layout.width else 0)
                sh=cq.Workplane('XY').box(w,h,thickness,centered=(False,False,False)).val()
                for o in layout.openings:
                    if o.x<x+w and o.x+o.length>x and o.y<y+h and o.y+o.width>y:
                        sh=sh.cut(cq.Workplane('XY').box(o.length,o.width,thickness+2,centered=(False,False,False)).translate((o.x-x,o.y-y,-1)).val())
                placements=[]
                for i,piece in enumerate(sh.Solids()):
                    bb=piece.BoundingBox();local=piece.translate((-bb.xmin,-bb.ymin,0))
                    outline=[(v.X,v.Y) for v in next(f for f in local.Faces() if f.normalAt().z<-.99).outerWire().Vertices()]
                    ops=[dict(kind='profile_cut',profile=outline)]
                    for o in layout.openings:
                        ox,oy=o.x-x-bb.xmin,o.y-y-bb.ymin
                        cw,ch=min(ox+o.length,bb.xlen)-max(ox,0),min(oy+o.width,bb.ylen)-max(oy,0)
                        if cw>0 and ch>0:ops.append(dict(kind='rectangular_opening',origin=[max(ox,0),max(oy,0)],size=[cw,ch],opening_id=o.id))
                    blank=dict(size=[bb.xlen,bb.ylen,thickness],panel_axes=[0,1],operations=ops)
                    pid=object_id+f'.sheet.{col}.{row}.{i}'
                    model.part(pid,local,parent=object_id,location=cq.Location(cq.Vector(x+bb.xmin,y+bb.ymin,floor['top'])),
                        blank=blank,material=product_id,label='Floor sheet');panels.append(pid)
                    model.requirement(pid+'.stock','stock_fit',[pid]);model.requirement(pid+'.valid','solid_valid',[pid])
                    model.requirement(pid+'.edges','panel_edge_support',[pid]+floor['parts']+blocks,threshold=0,direction_local=[0,0,-1])
                    placements.append(dict(object_id=pid,origin=[bb.xmin,bb.ymin],size=[bb.xlen,bb.ylen],operations=ops))
                if placements:sheets.append(dict(id=object_id+f'.stock.{col}.{row}',size=list(sheet_size),panels=placements))
    if blocks:_purchases(model,stock,{layout.rim.product_id:layout.rim},object_id,kerf if kerf is not None else (.125 if model.units=='in' else 3))
    model.demand(object_id+'.sheets',product_id=product_id,specification=dict(thickness=thickness,sheet=list(sheet_size)),
        object_ids=panels,purchase_unit='sheet',sheets=sheets,unresolved=list(unresolved))
    model.requirement(object_id+'.clear','collision_free',floor['parts']+blocks+panels,threshold=0)
    _clear_of_existing(model,blocks+panels,existing,object_id+'.interfaces')
    model.connection(object_id+'.installation',parts=floor['parts']+blocks+panels,description='Sheet joints have physical backing; fastening and load transfer need their own specification.',
        unresolved=list(unresolved)+['Specify backing connections and floor diaphragm fastening.'])
    model.expect(object_id+'.inventory',parts=blocks+panels,requirements=sorted(set(model.requirements)-before),
        connections=sorted(set(model.connections)-before_connections))
    model.drawing(object_id+'.plan',label='Floor decking',objects=panels,direction=vector_at(floor['location'],(0,0,1)),up=vector_at(floor['location'],(0,1,0)))
    model.step(object_id+'.install','Install the specified backing and cut sheets around the shared openings.',parts=blocks+panels,
               prerequisites=[floor['id']+'.frame'],view=object_id+'.plan')
    return dict(id=object_id,panels=panels,backing=blocks,top=floor['top']+thickness)


# One public flooring interface for rectangular framing and composed surfaces.
from .decking import PanelSpec, DeckRegion, FloorSurface, BackingDetail, FloorInstallation, build_deck


def deck_floor(model, floor, *, panel=None, regions=None, backing=None, installation=None, object_id=None, **legacy):
    """Lay out nominal panels and only required backing from shared floor inputs.

    Prefer PanelSpec. The earlier explicit product_id/thickness/sheet_size/gap
    form remains compatible with saved square-edge project scripts.
    """
    if panel is None:
        if regions is not None or backing is not None or installation is not None or object_id is not None:
            raise ValueError('The composed decking interface requires a PanelSpec.')
        return _legacy_deck_floor(model,floor,**legacy)
    if legacy:raise ValueError('Do not mix PanelSpec with legacy square-edge arguments.')
    return build_deck(model,floor,panel=panel,regions=regions,backing=backing,installation=installation,object_id=object_id)
