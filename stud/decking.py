"""Sheet layout and local backing for composed floor surfaces.

Region X follows sheet width; Y follows its strength/length axis. Geometry uses
nominal modules. Actual purchased sizes remain separate fabrication evidence.
"""
from dataclasses import dataclass, field, asdict
import math
import cadquery as cq
from .stock import cut_panel, cut_member, StockParts
from .cad import vector_at
from .framing import MemberProfile, _clear_of_existing
from .panel_edges import edge_intervals


def _positive(values):
    return all(math.isfinite(v) and v>0 for v in values)


@dataclass(frozen=True)
class PanelSpec:
    product_id: str
    thickness: float
    module: tuple = (48,96)
    actual_size: tuple | None = None
    edge: str = 'tongue_and_groove'
    joint_family: str | None = None
    unresolved: tuple = ()

    def __post_init__(self):
        if not self.product_id or len(self.module)!=2 or not _positive((*self.module,self.thickness)):
            raise ValueError('Panels need a product, positive thickness and width/strength-axis module dimensions.')
        if self.actual_size is not None and (len(self.actual_size)!=2 or not _positive(self.actual_size)):
            raise ValueError('Actual sheet dimensions must be two positive values.')
        if self.edge not in ('tongue_and_groove','square'):raise ValueError('Unknown panel edge system.')


@dataclass(frozen=True)
class DeckRegion:
    id: str
    outline: tuple | None = None
    origin: tuple = (0,0)
    angle: float = 0
    stagger: float | None = None

    def __post_init__(self):
        if not self.id or len(self.origin)!=2 or not all(math.isfinite(v) for v in (*self.origin,self.angle)):
            raise ValueError('A deck region needs an id, finite origin and angle.')
        if self.stagger is not None and not math.isfinite(self.stagger):raise ValueError('Stagger must be finite.')


@dataclass(frozen=True)
class FloorSurface:
    outline: tuple
    supports: tuple
    top: float
    openings: tuple = ()
    location: cq.Location = field(default_factory=cq.Location)

    def __post_init__(self):
        if not math.isfinite(self.top) or not self.supports or len(set(self.supports))!=len(self.supports):
            raise ValueError('A floor surface needs a finite top and unique named supports.')
        if len({o.id for o in self.openings})!=len(self.openings):raise ValueError('Opening ids must be unique.')


@dataclass(frozen=True)
class BackingDetail:
    stock: MemberProfile
    attachment: str
    unresolved: tuple = ()

    def __post_init__(self):
        if not isinstance(self.stock,MemberProfile) or self.stock.flange or not self.attachment:
            raise ValueError('Backing needs solid stock and an explicit attachment detail.')


@dataclass(frozen=True)
class FloorInstallation:
    fastening: str = ''
    adhesive: str = ''
    joint_gap: float | None = None
    unresolved: tuple = ()

    def __post_init__(self):
        if self.joint_gap is not None and (not math.isfinite(self.joint_gap) or self.joint_gap<0):
            raise ValueError('Installation joint gap must be finite and nonnegative.')


def _layer(points,z,thickness):
    if len(points)<3 or any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in points):
        raise ValueError('An outline needs at least three finite XY points.')
    shape=cq.Workplane('XY').polyline(points).close().extrude(thickness).translate((0,0,z)).val()
    if not shape.isValid() or shape.Volume()<=0:raise ValueError('Invalid floor outline.')
    return shape


def _box(x,y,z,w,h,d):
    return cq.Workplane('XY').box(w,h,d,centered=(False,False,False)).translate((x,y,z)).val()


def _overlap(a,b,pad=1e-6):
    return all(getattr(a,k+'min')<=getattr(b,k+'max')+pad and getattr(a,k+'max')>=getattr(b,k+'min')-pad for k in 'xyz')


def _surface(floor):
    if isinstance(floor,FloorSurface):return floor
    layout=floor['layout']
    return FloorSurface(((0,0),(layout.length,0),(layout.length,layout.width),(0,layout.width)),
                        tuple(floor['parts']),floor['top'],layout.openings,floor['location'])


def _regions(surface,regions,thickness):
    footprint=_layer(surface.outline,surface.top,thickness)
    for o in surface.openings:footprint=footprint.cut(_box(o.x,o.y,surface.top-1,o.length,o.width,thickness+2))
    if len({r.id for r in regions})!=len(regions) or sum(r.outline is None for r in regions)>1:
        raise ValueError('Region ids must be unique; at most one region can use the remaining floor area.')
    shapes={};remainder=footprint
    for r in regions:
        if r.outline is None:continue
        shape=footprint.intersect(_layer(r.outline,surface.top,thickness))
        if any(shape.intersect(other).Volume()>1e-6 for other in shapes.values()):raise ValueError('Deck regions overlap.')
        shapes[r.id]=shape;remainder=remainder.cut(shape)
    default=next((r for r in regions if r.outline is None),None)
    if default:shapes[default.id]=remainder
    elif remainder.Volume()>1e-6:raise ValueError('Deck regions do not cover the floor surface.')
    return footprint,shapes


def _panels(model,object_id,surface,regions,spec):
    footprint,areas=_regions(surface,regions,spec.thickness)
    panels=[];sheets=[];sx,sy=spec.module
    for region in regions:
        angle=math.radians(region.angle)
        frame=cq.Plane(origin=(*region.origin,surface.top),xDir=(math.cos(angle),math.sin(angle),0),normal=(0,0,1))
        area=areas[region.id].moved(frame.location.inverse)
        if not area.Solids():continue
        bounds=area.BoundingBox();stagger=sy/2 if region.stagger is None else region.stagger
        for col in range(math.floor(bounds.xmin/sx),math.ceil(bounds.xmax/sx)):
            x=col*sx;phase=(col%2)*stagger
            for row in range(math.floor((bounds.ymin-phase)/sy),math.ceil((bounds.ymax-phase)/sy)):
                y=row*sy+phase;cell=area.intersect(_box(x,y,0,sx,sy,spec.thickness));placements=[]
                for piece,solid in enumerate(sorted(cell.Solids(),key=lambda s:(s.Center().x,s.Center().y))):
                    if solid.Volume()<1e-7:continue
                    face=next(f for f in solid.Faces() if f.normalAt().z<-.99)
                    outline=[(v.X,v.Y) for v in face.outerWire().Vertices()]
                    local,loc,blank=cut_panel(cq.Plane.XY(),outline,spec.thickness)
                    offset=cq.Vector(*loc.toTuple()[0]);holes=[]
                    for wire in face.innerWires():
                        points=[(v.X-offset.x,v.Y-offset.y) for v in wire.Vertices()]
                        local=local.cut(cq.Workplane('XY').polyline(points).close().extrude(spec.thickness).val())
                        holes.append(dict(kind='profile_cutout',profile=points))
                    blank['operations'].extend(holes)
                    blank['geometry_basis']='nominal_module'
                    if spec.edge=='tongue_and_groove':
                        blank['factory_edges']=[dict(start=[u-offset.x,y-offset.y,0],end=[u-offset.x,y+sy-offset.y,0],
                            outward=[sign,0,0],role=role,family=spec.joint_family or spec.product_id)
                            for u,sign,role in ((x,-1,'groove'),(x+sx,1,'tongue'))]
                    pid=f'{object_id}.panel.{region.id}.c{col}.r{row}.p{piece}'
                    model.part(pid,local,location=frame.location*loc,parent=object_id+'.panels',
                               blank=blank,material=spec.product_id,label='Floor panel',color='#b89967')
                    panels.append(pid)
                    model.requirement(pid+'.valid','solid_valid',[pid]);model.requirement(pid+'.stock','stock_fit',[pid])
                    placements.append(dict(object_id=pid,origin=[offset.x-x,offset.y-y],size=blank['size'][:2],operations=blank['operations']))
                if placements:sheets.append(dict(id=f'{object_id}.stock.{region.id}.{col}.{row}',size=list(spec.module),panels=placements))
    return footprint,panels,sheets


def _backing(model,object_id,surface,panels,detail):
    if detail is None:return []
    width,depth=detail.stock.width,detail.stock.depth
    supports=list(surface.supports);bounds={p:model.shapes[p]['world'].BoundingBox() for p in supports+panels}
    # Compute all missing intervals first. Mating factory edges never enter this list.
    lines=[]
    for p in panels:
        hosts=[q for q in supports if _overlap(bounds[p],bounds[q])]
        mates=[q for q in panels if q!=p and _overlap(bounds[p],bounds[q])]
        missing,_=edge_intervals(model,p,hosts,mates)
        lines.extend(e.moved(surface.location.inverse) for e in missing)
    mask=_layer(surface.outline,surface.top-depth,depth)
    for o in surface.openings:mask=mask.cut(_box(o.x,o.y,surface.top-depth-1,o.length,o.width,depth+2))
    occupied=[]
    for p in supports:
        local=model.shapes[p]['world'].moved(surface.location.inverse)
        for f in local.Faces():
            if f.geomType()=='PLANE' and f.normalAt().z>.99 and abs(f.Center().z-surface.top)<1e-5:
                sh=cq.Solid.extrudeLinear(f.outerWire(),f.innerWires(),cq.Vector(0,0,-depth));occupied.append((sh,sh.BoundingBox()))
    stock=StockParts(model,parent=object_id+'.backing',demand_prefix=object_id+'.purchase.')
    blocks=[]
    for line in lines:
        if line.geomType()!='LINE':raise ValueError('Curved floor edges need an explicitly authored backing detail.')
        a,b=sorted([v.toTuple() for v in line.Vertices()]);delta=(cq.Vector(*b)-cq.Vector(*a)).normalized()
        # Extend to available end seats, then trim without notching existing framing.
        a=(cq.Vector(*a)-delta*width).toTuple();b=(cq.Vector(*b)+delta*width).toTuple()
        sh,loc,_=cut_member(a,b,(width,depth));sh=sh.moved(loc).intersect(mask)
        if not sh.Solids():continue
        bb=sh.BoundingBox()
        for other,other_bb in occupied:
            if _overlap(bb,other_bb):sh=sh.cut(other)
            if not sh.Solids():break
        for piece,solid in enumerate(sorted(sh.Solids(),key=lambda s:(s.Center().x,s.Center().y))):
            if solid.Volume()<1e-7 or sum(e.Length() for e in line.intersect(solid).Edges())<1e-7:continue
            local=solid.moved(loc.inverse);bb=local.BoundingBox();local=local.translate((0,-bb.ymin,0));placement=loc*cq.Location(cq.Vector(0,bb.ymin,0))
            outline=[(v.X,v.Y) for v in next(f for f in local.Faces() if f.normalAt().z<-.99).outerWire().Vertices()]
            blank=dict(size=[width,bb.ylen,depth],cut_length=bb.ylen,panel_axes=[0,1],operations=[dict(kind='profile_cut',profile=outline)])
            tag='_'.join(f'{v:.6g}' for v in (*a[:2],*b[:2]));pid=f'{object_id}.backing.{tag}.p{piece}'
            # Duplicate intervals have already been removed by occupied masks.
            stock.add(pid,(local,placement,blank),section=(width,depth),product_id=detail.stock.product_id,label='Local cut-edge backing')
            blocks.append(pid);occupied.append((solid,solid.BoundingBox()))
            model.requirement(pid+'.valid','solid_valid',[pid])
            world=model.shapes[pid]['world'];wb=world.BoundingBox()
            hosts=[q for q in supports if _overlap(wb,model.shapes[q]['world'].BoundingBox()) and world.distance(model.shapes[q]['world'])<1e-5]
            model.connection(pid+'.attachment',parts=[pid]+hosts,description=detail.attachment,
                unresolved=list(detail.unresolved)+list(detail.stock.unresolved)+([] if len(hosts)>=2 else ['Resolve backing end support.']),geometry_unresolved=len(hosts)<2)
            supports.append(pid)
    if blocks:stock.purchase(stock_lengths=detail.stock.stock_lengths)
    return blocks


def build_deck(model,floor,*,panel,object_id=None,regions=None,backing=None,installation=None):
    if not isinstance(panel,PanelSpec):raise ValueError('Supply a PanelSpec.')
    surface=_surface(floor)
    if object_id is None:
        if isinstance(floor,FloorSurface):raise ValueError('An independently composed surface needs a deck object_id.')
        object_id=floor['id']+'.deck'
    if regions is None:
        # Put square ends on the authored joist grid; callers can explicitly move the origin.
        origin=(0,0)
        if isinstance(floor,dict):
            joist=next((m for m in floor['layout'].members if m.role=='joist'),None)
            if joist:origin=(0,joist.start[1])
        regions=(DeckRegion('field',origin=origin),)
    if not regions:raise ValueError('At least one deck region is required.')
    installation=installation or FloorInstallation()
    existing=set(model.shapes);before=set(model.requirements);connections=set(model.connections)
    for p in surface.supports:
        if p not in model.shapes:raise ValueError(f'Missing floor support: {p}')
    model.assembly(object_id,'Floor decking',location=surface.location)
    model.assembly(object_id+'.panels','Floor panels',parent=object_id)
    model.assembly(object_id+'.backing','Local edge backing',parent=object_id)
    with model.batch():
        footprint,panels,sheets=_panels(model,object_id,surface,regions,panel)
        blocks=_backing(model,object_id,surface,panels,backing)
    if not panels:raise ValueError('The floor surface produced no panels.')
    hosts=list(surface.supports)+blocks;bounds={p:model.shapes[p]['world'].BoundingBox() for p in panels+hosts}
    for p in panels:
        supports=[q for q in hosts if _overlap(bounds[p],bounds[q])]
        mates=[q for q in panels if q!=p and _overlap(bounds[p],bounds[q])]
        model.requirement(p+'.edges','panel_edge_system',[p]+supports+mates,supports=supports,mates=mates,
            explanation='Every cut/square edge bears on framing; compatible retained T&G edges can mate without backing.')
    actual=panel.actual_size
    unresolved=list(panel.unresolved)+['Nominal module layout: reconcile actual sheet coverage, joint allowances and final cuts before fabrication.']
    model.demand(object_id+'.sheets',product_id=panel.product_id,specification=dict(thickness=panel.thickness,
        sheet=list(panel.module),actual_sheet=list(actual) if actual else None,edge=panel.edge,strength_axis=1,
        geometry_basis='nominal_module'),object_ids=panels,purchase_unit='sheet',sheets=sheets,unresolved=unresolved)
    model.requirement(object_id+'.clear','collision_free',panels+blocks)
    _clear_of_existing(model,panels+blocks,existing,object_id+'.interfaces')
    gaps=list(installation.unresolved)
    if not installation.fastening:gaps.append('Select the floor fastening schedule.')
    if not installation.adhesive:gaps.append('Specify adhesive or an approved installation without adhesive.')
    gaps.append('Installation fastener and adhesive purchase quantities remain unresolved.')
    model.connection(object_id+'.installation',parts=panels+blocks+list(surface.supports),
        description='Install staggered sheets around shared openings; T&G factory joints need no edge backing.',
        detail=asdict(installation),unresolved=gaps)
    model.drawing(object_id+'.plan',label='Subfloor panel layout',objects=panels,
        direction=vector_at(surface.location,(0,0,1)),up=vector_at(surface.location,(0,1,0)))
    model.step(object_id+'.install','Install local cut-edge support and the specified panel/fastening system.',parts=panels+blocks,
        connections=[object_id+'.installation'],view=object_id+'.plan',
        prerequisites=[floor['id']+'.frame'] if isinstance(floor,dict) else [])
    model.expect(object_id+'.inventory',parts=panels+blocks,requirements=sorted(set(model.requirements)-before),
        connections=sorted(set(model.connections)-connections))
    return dict(id=object_id,panels=panels,backing=blocks,top=surface.top+panel.thickness,sheets=len(sheets))
