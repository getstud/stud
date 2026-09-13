"""An L-shaped floor with shared openings and a rotated framing wing.

Generic geometry fixture, not a structurally sized construction design.
"""
import cadquery as cq
from stud.cad import Model
from stud.bulk import volume_demand
from stud.framing import MemberProfile
from stud.floors import (Bearing, Opening, HangerDetail, frame_floor, deck_floor,
    FloorSurface, DeckRegion, PanelSpec, BackingDetail, FloorInstallation)

model=Model('Composed T&G subfloor study',units='in')
OPENING=Opening('stairs',30,35,25,30)
JOIST=MemberProfile(2,9.5,'fixture.ijoist',(96,144,192),flange=1.125,web=.375,
    unresolved=('Select an engineered joist and verify loads.',))
RIM=MemberProfile(1.125,9.5,'fixture.rim',(96,144,192))
HEADER=MemberProfile(3.5,9.5,'fixture.header',(96,144,192))
HANGER=HangerDetail('fixture.hanger',2,7,.0625,('Select rated hardware and fasteners.',))
frames=[]
for name,length,width,location,openings in [
    ('main',144,144,cq.Location(),(OPENING,)),
    ('wing',96,48,cq.Location(cq.Vector(192,0,0),cq.Vector(0,0,1),90),())]:
    model.assembly(name,location=location)
    seats=[]
    for end,x in [('start',0),('end',length)]:
        pid=name+'.seat.'+end
        model.part(pid,cq.Workplane('XY').box(8,width,8,centered=(True,False,False)).translate((x,0,-8)),parent=name,material='fixture.concrete')
        seats.append(Bearing(pid,x,8,0))
        model.requirement(pid+'.valid','solid_valid',[pid])
    volume_demand(model,name+'.concrete',product_id='fixture.concrete',specification={},object_ids=[s.part_id for s in seats],purchase_unit='ft3')
    frames.append(frame_floor(model,object_id=name+'.frame',length=length,width=width,joist=JOIST,rim=RIM,
        bearings=seats,spacing=16,min_bearing=1.5,openings=openings,opening_stock=HEADER,hanger=HANGER,parent=name))

surface=FloorSurface(outline=((0,0),(192,0),(192,96),(144,96),(144,144),(0,144)),
    supports=tuple(p for f in frames for p in f['parts']),top=frames[0]['top'],openings=(OPENING,))
deck=deck_floor(model,surface,object_id='subfloor',
    panel=PanelSpec('fixture.tg_plywood',.703,actual_size=(47.5,95.875),
        unresolved=('Select panel product and span rating.',)),
    regions=(DeckRegion('main',origin=(0,2.125)),
             DeckRegion('wing',outline=((144,0),(192,0),(192,96),(144,96)),origin=(189.875,0),angle=90)),
    backing=BackingDetail(MemberProfile(3.5,1.5,'fixture.backing',(96,144)),
        'Local backing flush with joist tops; use the selected joist-compatible connection.',
        unresolved=('Resolve backing end attachments.',)),
    installation=FloorInstallation(joint_gap=.125,
        unresolved=('Select fastening, adhesive and the project diaphragm schedule.',)))
