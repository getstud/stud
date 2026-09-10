"""Appearance-only shed fixture. Envelope geometry, not construction documents."""
import cadquery as cq
from stud.cad import Model

SIDING = 'fiber_cement'
FINISH = 'sage paint'
model = Model('Shed appearance study — 10 × 8 feet', units='in')
model.assembly('shed', 'Shed')
model.assembly('enclosure', 'Siding', parent='shed')
model.assembly('openings', 'Door and windows', parent='shed')
model.assembly('roof', 'Roof and fascia', parent='shed')


def box(size, origin):
    return cq.Workplane('XY').box(*size, centered=(False,False,False)).translate(origin)


def part(key, shape, material, label, parent='openings', color='#eeeeea'):
    return model.part(key, shape, parent=parent, material=material, label=label, color=color)


part('slab', box((126,102,4),(-3,-3,0)), 'concrete', 'Concrete plinth', 'shed', '#aaa9a4')
gable=[(0,4),(120,4),(120,100),(60,130),(0,100)]
front=cq.Workplane('XZ').polyline(gable).close().extrude(.75).translate((0,.75,0))
front=front.cut(box((32,4,80),(16,-2,4))).cut(box((24,4,28),(82,-2,42)))
back=cq.Workplane('XZ').polyline(gable).close().extrude(.75).translate((0,96,0))
right=box((.75,94.5,96),(119.25,.75,4)).cut(box((4,28,28),(118,42,42)))
left=box((.75,94.5,96),(0,.75,4))
for key,shape,label in [('front',front,'Front gable siding, door left and window right'),('back',back,'Rear gable siding'),('left',left,'Left wall siding'),('right',right,'Right wall siding with one centered window')]:
    part('siding.'+key,shape,'siding.'+SIDING,label,'enclosure','#af7748' if SIDING=='cedar' else '#8a9c87')
model.demand('siding',product_id='siding.'+SIDING,specification={'material':SIDING,'finish':FINISH,'profile':'horizontal lap siding, 6 inch exposure'},
             object_ids=['siding.'+key for key in ('front','back','left','right')],purchase_unit='lot',unit='count',quantity=1)

part('door',box((32,1.25,80),(16,-.5,4)),'painted_wood','Single flush charcoal door',color='#343839')
for key,size,origin in [('left',(2,2,82),(14,-1,4)),('right',(2,2,82),(48,-1,4)),('head',(36,2,2),(14,-1,84))]:
    part('door.trim.'+key,box(size,origin),'white_trim','White door casing '+key)
part('door.handle',box((.75,2,4),(43,-2,42)),'black_steel','Vertical black door pull',color='#1c2023')

# Each window has one vertical and one horizontal mullion (four panes).
for key,origin,size in [('front',(82,-.25,42),(24,1,28)),('right',(119.25,42,42),(1,28,28))]:
    part('window.'+key+'.glass',box(size,origin),'clear_glass',key+' window glazing',color='#b1c5ce')
    x,y,z=origin
    if key=='front':
        bars=[('left',(2,2,32),(x-2,y-1,z-2)),('right',(2,2,32),(x+24,y-1,z-2)),('sill',(24,2,2),(x,y-1,z-2)),('head',(24,2,2),(x,y-1,z+28)),('vertical',(1,2,28),(x+11.5,y-1,z)),('horizontal',(24,2,1),(x,y-1,z+13.5))]
    else:
        bars=[('left',(2,2,32),(x,y-2,z-2)),('right',(2,2,32),(x,y+28,z-2)),('sill',(2,28,2),(x,y,z-2)),('head',(2,28,2),(x,y,z+28)),('vertical',(2,1,28),(x,y+13.5,z)),('horizontal',(2,28,1),(x,y,z+13.5))]
    for name,size,origin in bars:
        part('window.'+key+'.'+name,box(size,origin),'white_trim',key+' white window '+name)

for key,points in [('left',[(-6,97),(60,130),(60,131.5),(-6,98.5)]),('right',[(60,130),(126,97),(126,98.5),(60,131.5)])]:
    part('roof.'+key,cq.Workplane('XZ').polyline(points).close().extrude(108).translate((0,102,0)),
         'charcoal_metal','Charcoal standing seam roof '+key,'roof','#343839')
    # Front rake fascia is 3 inches deep and follows the same roof pitch.
    a,b=points[:2]
    fascia=[a,b,(b[0],b[1]-3),(a[0],a[1]-3)]
    part('fascia.'+key,cq.Workplane('XZ').polyline(fascia).close().extrude(1).translate((0,-5,0)),
         'white_trim','White front rake fascia '+key,'roof')
for key,x in [('left',-6),('right',125)]:
    part('eave.'+key,box((1,108,3),(x,-6,94)),'white_trim','White eave fascia '+key,'roof')
model.notes.append('Software rendering fixture with simplified enclosure solids. Dimensions and opening layout are intentional; structural/fabrication details are outside this appearance study.')
