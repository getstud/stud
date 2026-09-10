"""Project-owned shed framing study with explicit site-design omissions."""
import cadquery as cq
from stud.buildings import floor_frame, framed_wall, gable_roof


def shed(model, *, object_id='shed', length=120, depth=96, wall_height=96,
         door_width=36, window_width=26, slope=.5, wall_exceptions=None):
    """A detailed framing study whose site-dependent connections stay explicit."""
    floor=floor_frame(model,object_id=object_id+'.floor',length=length,depth=depth)
    z=floor['top'];d=3.5
    walls={}
    walls['front']=framed_wall(model,object_id=object_id+'.front',length=length,height=wall_height,
        location=cq.Location(cq.Vector(0,0,z)),openings=[dict(id='door',x=(length-door_width)/2,width=door_width,height=80)],
        exceptions=(wall_exceptions or {}).get('front'))
    walls['back']=framed_wall(model,object_id=object_id+'.back',length=length,height=wall_height,
        location=cq.Location(cq.Vector(length,depth,z),cq.Vector(0,0,1),180),
        openings=[dict(id='window',x=(length-window_width)/2,width=window_width,sill=36,height=36)],
        exceptions=(wall_exceptions or {}).get('back'))
    for side,origin,angle in [('left',(0,depth-d,z),-90),('right',(length,d,z),90)]:
        walls[side]=framed_wall(model,object_id=object_id+'.'+side,length=depth-2*d,height=wall_height,
            location=cq.Location(cq.Vector(*origin),cq.Vector(0,0,1),angle),exceptions=(wall_exceptions or {}).get(side))
    roof=gable_roof(model,object_id=object_id+'.roof',length=length,depth=depth,wall_top=z+wall_height,slope=slope,
        bearing_parts={side:walls[side]['top'][-1] for side in ('front','back')},
        end_bearing_parts={side:walls[side]['top'][-1] for side in ('left','right')})
    for side,wall in walls.items():
        for plate in wall['bottom']:
            model.requirement(plate+'.deck_support','support',[plate,floor['panels'][0 if side=='left' else -1 if side=='right' else 0]],threshold=1,units='in2')
    # Remove the one-panel shortcut for long front/back plates: supporting
    # contact is measured against the complete deck compound as an explicit
    # requirement set, without claiming that every sheet bears every plate.
    for side in ('front','back'):
        for plate in walls[side]['bottom']:
            model.requirements.pop(plate+'.deck_support',None)
            actual=[p for p in floor['panels'] if model.shapes[plate]['world'].distance(model.shapes[p]['world'])<.001]
            for panel_id in actual:model.requirement(plate+'.support.'+panel_id,'support',[plate,panel_id],threshold=1,units='in2')
    all_wall_parts=[part for wall in walls.values() for part in wall['parts']]
    model.connection(object_id+'.wall_floor',parts=all_wall_parts+floor['parts']+floor['panels'],
        description='Raise and brace each wall, fasten adjoining corner studs together, and fix the bottom plates through the deck into the rim or blocking below.',
        unresolved=['Specify foundation bearing, ground anchorage, and wall hold-downs for the site.'])
    model.step(object_id+'.erect_walls','Raise, square and brace the four completed walls on the platform. Fasten the corners and confirm the door rough opening.',
        parts=all_wall_parts,connections=[object_id+'.wall_floor'],prerequisites=[floor['id']+'.deck']+[wall['id']+'.frame' for wall in walls.values()],
        view=walls['front']['id']+'.elevation')
    model.steps[roof['id']+'.frame']['prerequisites'].append(object_id+'.erect_walls')
    model.requirement(object_id+'.interference','collision_free',[pid for pid in model.objects if pid.startswith(object_id+'.')],threshold=0,units='in3',
                      explanation='Native solid intersections between distinct framing and sheathing pieces.')
    model.notes += ['This packet details the frame and sheathing. Site foundation, load sizing, rated uplift/hold-down connections, roofing, flashing, cladding, door and window installation need project-specific details.',
                    'Member and fastener sizes in this study are fabrication inputs, not a structural analysis.']
    return dict(floor=floor,walls=walls,roof=roof)
