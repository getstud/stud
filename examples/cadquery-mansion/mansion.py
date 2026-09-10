"""Mixed two-storey workload: 509.9 m² of modular floors around a courtyard.

This is an architectural framing/performance study. Adjacent modules retain
paired end frames; foundations, structural sizing, inter-module connections,
weatherproofing and the courtyard interfaces remain authored review items.
"""
import cadquery as cq
from stud.buildings import floor_frame, framed_wall, gable_roof
from stud.cad import vector_at


def residence(model, *, bay=4267.2, window_width=1000, local_window_width=1200,
              wall_height=2743.2, slope=.45, bore_diameter=12, rotation=0,
              include_guest=True):
    world=cq.Location(cq.Vector(0,0,0),cq.Vector(0,0,1),rotation)
    model.assembly('house','Courtyard residence',location=world)
    rooms={
        'west':['kitchen','dining','living','guest'],
        'east':['library','music','family','guest'],
        'north':['hall','stairs','gallery','suite','study','office'],
    }
    # The north range bridges the two perpendicular wings.
    origins={'west':((bay,0,0),90),'east':((6*bay,0,0),90),'north':((0,4*bay,0),0)}
    floors=[];roofs=[];feature_walls=[]
    for wing,names in rooms.items():
        origin,angle=origins[wing]
        parent=model.assembly('house.'+wing,wing.title()+' wing',parent='house',
            location=cq.Location(cq.Vector(*origin),cq.Vector(0,0,1),angle))
        if not include_guest and wing=='east':names=names[:-1]
        for level in range(2):
            z=level*(wall_height+159.05)
            for index,room in enumerate(names):
                module=f'house.{wing}.level{level+1}.{room}'
                model.assembly(module,room.title(),parent=parent,location=cq.Location(cq.Vector(index*bay,0,z)))
                floor=floor_frame(model,object_id=module+'.floor',parent=module,length=bay,depth=bay,
                    stair_opening=dict(x=1500,y=700,width=1000,depth=2200) if wing=='north' and room=='stairs' and level==1 else None)
                floors.append(floor['id'])
                walls={};d=89;h=wall_height
                for side,origin_,angle_ in [('front',(0,0,159.05),0),('back',(bay,bay,159.05),180)]:
                    width=local_window_width if wing=='west' and room=='kitchen' and side=='front' and level==0 else window_width
                    opening=dict(id='window',x=(bay-width)/2,width=width,sill=900,height=1100)
                    bore={'stud.at_406_4':dict(bore=dict(x=19,z=700,diameter=bore_diameter))} if wing=='west' and room=='kitchen' and side=='front' and level==0 else None
                    walls[side]=framed_wall(model,object_id=module+'.'+side,parent=module,length=bay,height=h,
                        location=cq.Location(cq.Vector(*origin_),cq.Vector(0,0,1),angle_),openings=[opening],exceptions=bore)
                for side,origin_,angle_,outside in [('left',(0,bay-d,159.05),-90,index==0),('right',(bay,d,159.05),90,index==len(names)-1)]:
                    openings=[] if outside else [dict(id='passage',x=1400,width=1100,height=2100)]
                    walls[side]=framed_wall(model,object_id=module+'.'+side,parent=module,length=bay-2*d,height=h,
                        location=cq.Location(cq.Vector(*origin_),cq.Vector(0,0,1),angle_),openings=openings,sheathing=outside)
                if room in ('kitchen','stairs') and level==0:feature_walls.append(walls['front']['id'])
                if level==1:
                    roof=gable_roof(model,object_id=module+'.roof',parent=module,length=bay,depth=bay,
                        wall_top=159.05+h,slope=slope,
                        bearing_parts={side:walls[side]['top'][-1] for side in ('front','back')},
                        end_bearing_parts={side:walls[side]['top'][-1] for side in ('left','right')},
                        gable_ends=[side for side,outer in [('left',index==0),('right',index==len(names)-1)] if outer])
                    roofs.append(roof['id'])
    model.drawing('house.overview',label='Courtyard residence: two floors and three wings',objects=['house'],
        direction=vector_at(world,(1,-1,1)),up=vector_at(world,(0,0,1)),dimensions=[],hidden_lines=False)
    model.drawing('house.floor_overview',label='Upper floor and stair opening',objects=[f for f in floors if '.level2.' in f],
        direction=vector_at(world,(0,0,1)),up=vector_at(world,(0,1,0)),dimensions=[],hidden_lines=False)
    model.notes += ['Architectural framing and performance study: 14 room bays on each of two storeys, 509.9 square metres of floor platforms at the default dimensions.',
        'Adjacent modules retain paired end frames. Specify their load paths, fasteners, inter-storey bearing and wing junctions before construction.',
        'Foundation, member sizing, egress, fire separation, roof drainage, flashing, cladding, windows and doors require project-specific design. No structural analysis is implied.']
    return dict(floors=floors,roofs=roofs,feature_walls=feature_walls,
                area_m2=len(floors)*bay*bay/1_000_000)
