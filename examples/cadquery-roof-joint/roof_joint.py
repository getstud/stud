"""Project-owned rafter bearing sample with explicit fabrication data."""
import cadquery as cq
from stud.cad import point_at
from stud.construction import cut_rafter, imperial_model


def roof_joint(model, *, object_id='roof_joint', slope=0.5, run=20, seat=3.5):
    imperial_model(model)
    model.assembly(object_id,'Roof bearing detail')
    thickness,height=1.5,5.5
    rafter,rotation,fabrication=cut_rafter(slope=slope,run=run,seat=seat)
    length=fabrication['cut_length']
    rafter_id=object_id+'.rafter'
    model.part(rafter_id,rafter,parent=object_id,material='lumber.1.5x5.5',location=rotation,
               blank=fabrication)
    plate_id=object_id+'.plate'
    plate=cq.Workplane('XY').box(thickness,seat,1.5,centered=(False,False,False))
    model.part(plate_id,plate,parent=object_id,location=cq.Location(cq.Vector(0,0,seat*slope-1.5)),
               material='lumber.1.5x'+str(seat),blank={'size':[thickness,seat,1.5],'cut_length':thickness,
                   'operations':[{'kind':'square_cut','finished_length':thickness}]})
    model.requirement(object_id+'.bearing','support',[rafter_id,plate_id],threshold=thickness*seat,units='in2')
    model.requirement(object_id+'.collision','collision',[rafter_id,plate_id],threshold=0,units='in3')
    for pid in [rafter_id,plate_id]:
        model.requirement(pid+'.blank','stock_fit',[pid])
    model.reference(rafter_id,'seat_front',point=point_at(rotation.inverse,(0,0,seat*slope)))
    model.reference(rafter_id,'seat_back',point=point_at(rotation.inverse,(0,seat,seat*slope)))
    model.dimension(object_id+'.seat',rafter_id+':seat_front',rafter_id+':seat_back',label='Bearing seat')
    model.drawing(object_id+'.detail',objects=[object_id],direction=(1,0,0),dimensions=[object_id+'.seat'])
    for part,section,cut in [(rafter_id,[thickness,height],length),(plate_id,[1.5,seat],thickness)]:
        model.demand(part+'.stock',product_id='lumber.'+'x'.join(map(str,section)),
            specification={'material':'softwood','section':section},object_ids=[part],unit='in',purchase_unit='board',
            stock_lengths=[96],cuts=[{'object_id':part,'length':cut}],kerf=.125)
    model.connection(object_id+'.seat_joint',parts=[rafter_id,plate_id],
        description='Cut the plumb ends and flat seat shown, then seat the rafter fully against the plate. This isolated bearing sample does not specify uplift or lateral restraint.',
        unresolved=['A complete roof needs a separately specified uplift and lateral connection.'])
    model.step(object_id+'.seat_sample','Mark the rafter in its 1 1/2 x 5 1/2 in rectangular blank, cut both plumb ends, and make the birdsmouth. Check the full bearing face against the plate.',
               parts=[rafter_id,plate_id],connections=[object_id+'.seat_joint'],view=object_id+'.detail')
    return [rafter_id,plate_id]
