"""Editable foundation recipes; dimensions are geometric fixtures, not sizing.

Local grade is Z=0. Common bearing interfaces are derived from these datums.
Each builder can be composed under a parent with a rigid assembly placement.
"""
import math

import cadquery as cq

from stud.bulk import volume_demand
from stud.cad import point_at, vector_at
from stud.construction import imperial_model
from stud.solids import prism, round_member
from stud.stock import Plane, StockParts, cut_member


def rectangle(x, y, width, length):
    return [(x,y),(x+width,y),(x+width,y+length),(x,y+length)]


def layer(width, length, bottom, depth, *, inset=0):
    return prism(rectangle(inset,inset,width-2*inset,length-2*inset),depth,
                 frame=cq.Plane(origin=(0,0,bottom),normal=(0,0,1)))


def ring(width, length, bottom, depth, *, outside=0, inside=8):
    return prism(rectangle(-outside,-outside,width+2*outside,length+2*outside),depth,
                 holes=[rectangle(inside,inside,width-2*inside,length-2*inside)],
                 frame=cq.Plane(origin=(0,0,bottom),normal=(0,0,1)))


class Parts:
    """Recipe-local bookkeeping; material and foundation choices stay here."""
    def __init__(self, model, object_id, width, length, parent, location):
        imperial_model(model)
        if not all(math.isfinite(v) and v > 48 for v in (width,length)):
            raise ValueError('This fixture needs finite plan dimensions over 48 inches.')
        self.model=model; self.id=object_id; self.width=width; self.length=length
        model.assembly(object_id,parent=parent,location=location)
        self.world=model._parent_location(object_id)
        self.groups={}; self.parts=[]

    def add(self, key, shape, product='concrete', color='#aeb4b7'):
        pid=self.id+'.'+key
        self.model.part(pid,shape,parent=self.id,material=product,label=key.replace('_',' '),color=color)
        self.model.requirement(pid+'.valid','solid_valid',[pid])
        self.parts.append(pid); self.groups.setdefault(product,[]).append(pid)
        return pid

    def bearing(self, upper, lower, area):
        self.model.requirement(upper+'.on.'+lower,'support',[upper,lower],threshold=area,
                               direction=vector_at(self.world,(0,0,-1)))

    def finish(self, *, unresolved=()):
        model=self.model
        for product, ids in self.groups.items():
            if product=='insulation':
                model.demand(self.id+'.purchase.insulation',product_id=product,
                             specification={'material':product,'thickness':2},object_ids=ids,
                             unit='in2',purchase_unit='sheet',
                             unresolved=['Continuous insulation envelopes: select panels and author cutting layouts.'])
                continue
            volume_demand(model,self.id+'.purchase.'+product,product_id=product,
                          specification={'material':product,'selection':'Unspecified fixture product'},
                          object_ids=ids,purchase_unit='yd3',purchase_increment='.25',
                          unresolved=['Select the material/product and supplier delivery basis.'])
        # Reinforcement and hardware intentionally embed in concrete; restrict
        # interference checks to the unembedded foundation body/layer parts.
        model.requirement(self.id+'.body_interference','collision_free',self.parts)
        first=self.parts[0]
        start=model.reference(first,'plan_origin',point=(0,0,0))
        end=model.reference(first,'plan_width',point=(self.width,0,0))
        dim=self.id+'.width'
        model.dimension(dim,start,end,label='Foundation layout width')
        model.drawing(self.id+'.plan',objects=self.parts,direction=vector_at(self.world,(0,0,1)),
                      up=vector_at(self.world,(0,1,0)),dimensions=[dim])
        model.drawing(self.id+'.section',objects=self.parts,direction=vector_at(self.world,(0,-1,0)),
                      up=vector_at(self.world,(0,0,1)),
                      section={'origin':point_at(self.world,(0,self.length/2,0)),
                               'normal':vector_at(self.world,(0,1,0))})
        connection=self.id+'.design_basis'
        model.connection(connection,parts=self.parts,
                         description='Resolve the foundation design and its connection to the building.',
                         unresolved=[
                             'Fixture dimensions: establish soil bearing, settlement, groundwater and site loads.',
                             'Select jurisdiction, frost protection and heated/unheated operating conditions.',
                             'Design reinforcement, construction joints and building anchorage for the load path.',
                             'Detail drainage, moisture/radon barriers, insulation and penetrations.',
                             *unresolved])
        model.step(self.id+'.review','Review this geometric study against the site design before construction.',
                   parts=self.parts,connections=[connection],view=self.id+'.section')
        model.notes.append('Foundation fixture only: native contact and volume checks do not establish structural capacity.')
        return {'assembly':self.id,'parts':self.parts,'width':self.width,'length':self.length}


def monolithic_slab(model, *, object_id='foundation', width=144, length=112, parent=None, location=None):
    p=Parts(model,object_id,width,length,parent,location)
    base=p.add('aggregate',layer(width,length,-16,4),'aggregate','#ad9d82')
    # One physical pour: the slab and perimeter are fused before registration.
    body=layer(width,length,-4,4).fuse(ring(width,length,-12,8,inside=12)).clean()
    slab=p.add('slab_and_edge',body)
    p.bearing(slab,base,width*length-(width-24)*(length-24))
    fill=p.add('compacted_fill',layer(width,length,-12,8,inset=12),'fill','#ab9275')
    p.bearing(slab,fill,(width-24)*(length-24))
    p.bearing(fill,base,(width-24)*(length-24))
    return p.finish(unresolved=['Specify compaction and control-joint layout.'])


def stem_wall_slab(model, *, object_id='foundation', width=144, length=112, parent=None, location=None):
    p=Parts(model,object_id,width,length,parent,location)
    footing=p.add('strip_footing',ring(width,length,-40,8,outside=4,inside=12))
    wall=p.add('stem_wall',ring(width,length,-32,40))
    p.bearing(wall,footing,width*length-(width-16)*(length-16))
    base=p.add('aggregate',layer(width,length,-4,4,inset=8),'aggregate','#ad9d82')
    slab=p.add('floor_slab',layer(width,length,0,4,inset=8))
    p.bearing(slab,base,(width-16)*(length-16))
    fill=p.add('compacted_fill',layer(width,length,-32,28,inset=8),'fill','#ab9275')
    p.bearing(base,fill,(width-16)*(length-16))
    return p.finish(unresolved=['Specify fill compaction, garage floor slope and threshold.'])


def _enclosed(model, object_id, width, length, parent, location, *, height, slab, walkout=False):
    p=Parts(model,object_id,width,length,parent,location)
    bottom=-height
    footing=p.add('strip_footing',ring(width,length,bottom-8,8,outside=4,inside=12))
    body=ring(width,length,bottom,height+8)
    bearing_area=width*length-(width-16)*(length-16)
    if walkout:
        # Opening starts above the lower slab, leaving the footing/wall bearing intact.
        opening=prism(rectangle(width/2-18,-1,36,10),80,
                      frame=cq.Plane(origin=(0,0,bottom+8),normal=(0,0,1)))
        body=body.cut(opening).clean()
    wall=p.add('foundation_wall',body)
    p.bearing(wall,footing,bearing_area)
    if slab:
        base=p.add('aggregate',layer(width,length,bottom,4,inset=8),'aggregate','#ad9d82')
        floor=p.add('floor_slab',layer(width,length,bottom+4,4,inset=8))
        p.bearing(floor,base,(width-16)*(length-16))
    notes=['Compose the raised floor and its beam/column pads from the actual load layout.',
           'Check lateral earth pressure, wall restraint and waterproofing.']
    if walkout:notes.append('Design retained grades/steps beside the walkout, opening lintel, threshold and drainage.')
    return p.finish(unresolved=notes)


def crawlspace(model, *, object_id='foundation', width=144, length=112, parent=None, location=None):
    return _enclosed(model,object_id,width,length,parent,location,height=32,slab=False)


def basement(model, *, object_id='foundation', width=144, length=112, parent=None, location=None):
    return _enclosed(model,object_id,width,length,parent,location,height=96,slab=True)


def walkout_basement(model, *, object_id='foundation', width=144, length=112, parent=None, location=None):
    return _enclosed(model,object_id,width,length,parent,location,height=96,slab=True,walkout=True)


def mat_slab(model, *, object_id='foundation', width=144, length=112, parent=None, location=None):
    p=Parts(model,object_id,width,length,parent,location)
    base=p.add('aggregate',layer(width,length,-16,4),'aggregate','#ad9d82')
    mat=p.add('structural_mat',layer(width,length,-12,12))
    p.bearing(mat,base,width*length)
    return p.finish(unresolved=['Design two-way mat action, punching shear, settlement and reinforcement.'])


def _supported(model, object_id, width, length, parent, location, *, system):
    p=Parts(model,object_id,width,length,parent,location)
    concrete_beams=system in ('drilled','piles')
    stock=StockParts(model,parent=object_id,demand_prefix=object_id+'.')
    stock_ids=[]; supports=[]
    for row,y in [('front',12),('back',length-12)]:
        row_supports=[]
        for station,x in [('left',12),('right',width-12)]:
            key=row+'.'+station
            if system in ('pier','post'):
                pad=p.add(key+'.pad',prism(rectangle(x-10,y-10,20,20),8,
                          frame=cq.Plane(origin=(0,0,-40),normal=(0,0,1))))
                if system=='pier':
                    support=p.add(key+'.pier',round_member((x,y,-32),(x,y,8),12))
                    p.bearing(support,pad,math.pi*6**2)
                else:
                    # Real rectangular treated stock with original blank/cut demand.
                    support=object_id+'.'+key+'.post'
                    result=cut_member((x,y,-32),(x,y,8),(5.5,5.5),
                                      start_plane=Plane((0,0,-32),(0,0,-1)),
                                      end_plane=Plane((0,0,8),(0,0,1)),up=(1,0,0))
                    stock.add(support,result,section=(5.5,5.5),product_id='treated.6x6')
                    stock_ids.append(support)
                    p.bearing(support,pad,5.5**2)
            elif system=='helical':
                shaft=round_member((x,y,-120),(x,y,8),3,inner_diameter=2.5)
                # Actual pitched helicoid from a radial section, not a flat disk.
                helix=cq.Wire.makeHelix(3,3,1.5)
                section=cq.Workplane('XZ').polyline([(1.25,0),(6,0),(6,.375),(1.25,.375)]).close()
                blade=section.sweep(helix,isFrenet=True).val().translate((x,y,-114))
                shape=shaft.fuse(blade).clean()
                support=p.add(key+'.helical_pile',shape,'steel_pile','#647889')
            else:
                depth=120 if system=='drilled' else 180
                support=p.add(key+'.'+('drilled_shaft' if system=='drilled' else 'driven_pile'),
                              round_member((x,y,-depth),(x,y,0),12),
                              'concrete' if system=='drilled' else 'precast_pile')
                cap=p.add(key+'.cap',prism(rectangle(x-10,y-10,20,20),8))
                p.bearing(cap,support,math.pi*6**2)
                support=cap
            row_supports.append(support)
        if concrete_beams:
            beam=p.add(row+'.grade_beam',prism(rectangle(2,y-6,width-4,12),12,
                       frame=cq.Plane(origin=(0,0,8),normal=(0,0,1))))
            for support in row_supports:p.bearing(beam,support,20*12)
        else:
            beam=object_id+'.'+row+'.beam'
            result=cut_member((0,y,15.25),(width,y,15.25),(5.5,7.25))
            stock.add(beam,result,section=(5.5,7.25),product_id='treated.6x8')
            stock_ids.append(beam)
            if system=='pier':
                # Area of the centered 5.5-inch strip across a 12-inch circle.
                half=5.5/2; radius=6
                area=2*(half*math.sqrt(radius**2-half**2)+radius**2*math.asin(half/radius))
            elif system=='post':area=5.5**2
            else:area=math.pi*(3**2-2.5**2)/4
            for support in row_supports:p.bearing(beam,support,area)
        supports.extend(row_supports)
    if stock_ids:
        for demand_id in stock.purchase(stock_lengths=[96,144,192],material='preservative-treated wood'):
            model.demands[demand_id]['unresolved'].append('Select lumber species, grade, treatment and a sourced sizing basis.')
    # Whole piles are bought as selected units, not yards of constituent steel.
    if system in ('helical','piles'):
        product='steel_pile' if system=='helical' else 'precast_pile'
        ids=p.groups.pop(product)
        model.demand(object_id+'.pile_units',product_id=product,specification={'selection':'Fixture only'},
                     object_ids=ids,quantity=len(ids),unit='each',purchase_unit='each',
                     unresolved=['Select rated pile/product, installation acceptance and durability details.'])
    p.parts.extend(stock_ids)
    result=p.finish(unresolved=[
        'Design support spacing, lateral restraint and uplift connections through the raised floor.',
        'Establish installation/embedment requirements, shaft capacity, durability and any group effects.'])
    return result


def pier_and_beam(model, *, object_id='foundation', width=144, length=112, parent=None, location=None):
    return _supported(model,object_id,width,length,parent,location,system='pier')


def post_frame(model, *, object_id='foundation', width=144, length=112, parent=None, location=None):
    return _supported(model,object_id,width,length,parent,location,system='post')


def pile_and_cap(model, *, object_id='foundation', width=144, length=112, parent=None, location=None):
    return _supported(model,object_id,width,length,parent,location,system='piles')


def drilled_pier_and_grade_beam(model, *, object_id='foundation', width=144, length=112, parent=None, location=None):
    return _supported(model,object_id,width,length,parent,location,system='drilled')


def helical_pile_and_beam(model, *, object_id='foundation', width=144, length=112, parent=None, location=None):
    return _supported(model,object_id,width,length,parent,location,system='helical')


def frost_protected_slab(model, *, object_id='foundation', width=144, length=112, parent=None, location=None):
    p=Parts(model,object_id,width,length,parent,location)
    p.add('slab_and_edge',layer(width,length,-4,4).fuse(ring(width,length,-12,8,inside=12)).clean())
    p.add('under_slab_insulation',layer(width,length,-6,2,inset=12),'insulation','#a5c9da')
    p.add('vertical_insulation',ring(width+4,length+4,-14,14,inside=2).translate((-2,-2,0)),
          'insulation','#a5c9da')
    p.add('insulation_wing',ring(width,length,-16,2,outside=26,inside=-2),'insulation','#a5c9da')
    return p.finish(unresolved=['Select a sourced heated/unheated FPSF design; fixture insulation dimensions are unverified.',
                               'Provide subbase/infill, corner insulation and protected insulation terminations.'])


def rubble_trench(model, *, object_id='foundation', width=144, length=112, parent=None, location=None):
    p=Parts(model,object_id,width,length,parent,location)
    trench=p.add('compacted_stone_trench',ring(width,length,-40,32,outside=4,inside=12),'aggregate','#ad9d82')
    beam=p.add('grade_beam',ring(width,length,-8,16))
    p.bearing(beam,trench,width*length-(width-16)*(length-16))
    return p.finish(unresolved=['Establish an accepted rubble/stone foundation design and soil/filter compatibility.',
                               'Detail the drain, discharge, compaction and frost/settlement performance.'])


RECIPES = {builder.__name__: builder for builder in (
    monolithic_slab, stem_wall_slab, crawlspace, basement, walkout_basement,
    pier_and_beam, post_frame, mat_slab, pile_and_cap, drilled_pier_and_grade_beam,
    helical_pile_and_beam, frost_protected_slab, rubble_trench)}
