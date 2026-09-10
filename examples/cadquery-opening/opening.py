"""Project-owned rotated opening and mirrored corner example."""
import math
import cadquery as cq
from stud.construction import imperial_model


def rotated_opening(model, *, object_id='opening', width=36, height=84, angle=30,
                    origin=(0,0,0), mirrored_detail=False):
    imperial_model(model)
    model.assembly(object_id,'Rotated opening',location=cq.Location(cq.Vector(*origin),cq.Vector(0,0,1),angle))
    t,depth,header=1.5,3.5,5.5
    parts=[]
    for name,size,offset in [('left_jamb',(t,depth,height),(0,0,0)),
                             ('right_jamb',(t,depth,height),(width+t,0,0)),
                             ('header',(width+2*t,depth,header),(0,0,height))]:
        pid=object_id+'.'+name
        shape=cq.Workplane('XY').box(*size,centered=(False,False,False))
        cut_length=height if name!='header' else width+2*t
        model.part(pid,shape,parent=object_id,location=cq.Location(cq.Vector(*offset)),
                   blank={'size':list(size),'cut_length':cut_length,'operations':[{'kind':'square_cut','finished_length':cut_length}]},
                   material='lumber.1.5x3.5' if name!='header' else 'lumber.3.5x5.5')
        model.requirement(pid+'.blank','stock_fit',[pid])
        parts.append(pid)
    model.reference(parts[0],'clear_left',point=(t,0,0))
    model.reference(parts[1],'clear_right',point=(0,0,0))
    model.requirement(object_id+'.clear_width','length',[parts[0]+':clear_left',parts[1]+':clear_right'],threshold=width)
    model.requirement(object_id+'.header.left','support',[parts[2],parts[0]],threshold=t*depth,units='in2')
    model.requirement(object_id+'.header.right','support',[parts[2],parts[1]],threshold=t*depth,units='in2')
    # The asymmetric, bored corner is mirrored in the solid, never in viewer transforms.
    detail=cq.Workplane('XY').polyline([(0,0),(3,0),(3,1),(1,3),(0,3)]).close().extrude(.25)
    detail=detail.cut(cq.Workplane('XY').circle(5/32).extrude(.25).translate((.625,.625,0)))
    if mirrored_detail:
        detail=detail.mirror('YZ').translate((3,0,0))
    pid=object_id+'.corner_detail'
    profile=[(0,0),(3,0),(3,1),(1,3),(0,3)]
    if mirrored_detail:profile=[(3-x,y) for x,y in profile]
    model.part(pid,detail,parent=object_id,location=cq.Location(cq.Vector(t,0,height+header)),
               material='steel.plate.3x3x0.25',
               blank={'size':[3,3,.25],'operations':[{'kind':'profile_cut','profile':profile},
                   {'kind':'bore','diameter':5/16,'center':[2.375 if mirrored_detail else .625,.625],'through':True,'axis':'Z'}]},color='#758185')
    model.requirement(pid+'.blank','stock_fit',[pid])
    model.dimension(object_id+'.width',parts[0]+':clear_left',parts[1]+':clear_right',label='Clear opening')
    model.drawing(object_id+'.elevation',objects=[object_id],direction=(math.sin(math.radians(angle)),-math.cos(math.radians(angle)),0),
                  dimensions=[object_id+'.width'])
    model.drawing(object_id+'.corner_plan',label='Corner sample: profile and bore',objects=[pid],direction=(0,0,1),
        up=(-math.sin(math.radians(angle)),math.cos(math.radians(angle)),0),detail_of=object_id+'.elevation')
    for key, ids, section, lengths in [('jambs',parts[:2],[t,depth],[height,height]),
                                      ('header',[parts[2]],[depth,header],[width+2*t])]:
        model.demand(object_id+'.'+key,product_id='lumber.'+'x'.join(map(str,section)),
            specification={'material':'softwood','section':section},object_ids=ids,unit='in',purchase_unit='board',
            stock_lengths=[96],cuts=[dict(object_id=part,length=length) for part,length in zip(ids,lengths)],kerf=.125)
    model.demand(object_id+'.steel',product_id='steel.plate.3x3x0.25',specification={'material':'steel','size':[3,3,.25]},
                 object_ids=[pid],quantity=1,purchase_unit='each')
    model.connection(object_id+'.joint',parts=parts,
        description='Seat the header on both jamb ends. Clamp square and fasten with two #10 x 3 in screws into each jamb.',
        hardware={'product_id':'screws.no10x3','count':4})
    model.demand(object_id+'.screws',product_id='screws.no10x3',specification={'gauge':'#10','length':3,'type':'wood'},
                 object_ids=parts,quantity=4,pack_size=50,purchase_unit='pack')
    model.step(object_id+'.assemble','Cut the jambs and header to the listed lengths, label them, and assemble the opening on a flat surface.',
               parts=parts,connections=[object_id+'.joint'],view=object_id+'.elevation')
    model.step(object_id+'.corner','Cut and bore the separate mirrored corner sample using its local blank dimensions; this sample is not a specified structural connector.',
               parts=[pid],prerequisites=[object_id+'.assemble'],view=object_id+'.corner_plan')
    return parts+[pid]
