"""Reusable CadQuery proving components with explicit fabrication information.

These definitions describe geometry and assembly intent, not structural design
approval. Projects remain ordinary Python and can make deliberate local edits.
"""
import math
import cadquery as cq

from .cad import inches, point_at, vector_at


def workbench(model, *, object_id='bench', width=inches(72), depth=inches(24),
              height=inches(36), shelf_height=inches(10), dog_hole=(200, 100), location=None):
    t, b, panel = inches(1.5), inches(3.5), inches(.75)
    if width <= 2*t or depth <= 2*b or height <= shelf_height + 2*b + panel:
        raise ValueError('Workbench dimensions leave no room for its frame and shelf.')
    model.assembly(object_id, 'Workbench', location=location)
    frame = model.assembly(object_id+'.frame', 'Frame', parent=object_id)
    surfaces = model.assembly(object_id+'.surfaces', 'Top and shelf', parent=object_id)
    cuts, legs, upper_rails, lower_rails = [], [], [], []
    lumber_spec = {'material': 'softwood', 'section_mm': [t, b], 'grade': 'construction'}
    plywood_spec = {'material': 'plywood', 'thickness_mm': panel, 'sheet_mm': [inches(96), inches(48)]}

    def member(key, size, origin, cut_length, group):
        part_id = object_id+'.'+key
        shape = cq.Workplane('XY').box(*size, centered=(False, False, False))
        model.part(part_id, shape, parent=frame, label=key.replace('.', ' ').title(),
                   location=cq.Location(cq.Vector(*origin)), material='lumber.2x4',
                   blank={'size_mm': list(size), 'cut_length_mm': cut_length,
                          'operations': [{'kind': 'square_cut', 'finished_length_mm': cut_length}]})
        model.requirement(part_id+'.blank', 'stock_fit', [part_id], explanation='Finished member fits its stated stock blank.')
        cuts.append({'object_id': part_id, 'length_mm': cut_length})
        group.append(part_id)
        return part_id

    with model.batch():
        for side, x in [('left', 0), ('right', width-t)]:
            for end, y in [('front', 0), ('back', depth-b)]:
                member(f'leg.{side}.{end}', (t,b,height-panel), (x,y,0), height-panel, legs)
        for level, z, group in [('upper', height-panel-b, upper_rails), ('lower', shelf_height-b, lower_rails)]:
            for end, y in [('front', 0), ('back', depth-t)]:
                rail = member(f'rail.{level}.{end}', (width-2*t,t,b), (t,y,z), width-2*t, group)
                for side in ('left','right'):
                    model.requirement(rail+'.'+side+'.contact', 'contact', [rail, f'{object_id}.leg.{side}.{end}'],
                                      threshold=t*b, units='mm2', explanation='Square rail end contacts its leg.')
        for side, x in [('left',0),('right',width-t)]:
            rail = member('rail.upper.'+side, (t,depth-2*b,b), (x,b,height-panel-b), depth-2*b, upper_rails)
            for end in ('front','back'):
                model.requirement(rail+'.'+end+'.contact', 'contact', [rail,f'{object_id}.leg.{side}.{end}'],
                                  threshold=t*b, units='mm2', explanation='Side rail bears against the leg face.')

    top_id, shelf_id = object_id+'.top', object_id+'.shelf'
    top = cq.Workplane('XY').box(width,depth,panel,centered=(False,False,False))
    operations = [{'kind':'panel_cut', 'finished_size_mm':[width,depth,panel]}]
    if dog_hole:
        hx, hy = dog_hole
        radius = inches(.375)
        if not radius < hx < width-radius or not radius < hy < depth-radius:
            raise ValueError('The deliberate dog hole must remain inside the worktop.')
        boring = cq.Workplane('XY').circle(radius).extrude(panel).translate((hx,hy,0))
        top = top.cut(boring)
        operations.append({'kind':'bore', 'diameter_mm':radius*2, 'center_mm':[hx,hy], 'through':True})
    shelf_size = (width-2*t, depth-panel*2, panel)
    shelf = cq.Workplane('XY').box(*shelf_size,centered=(False,False,False))
    with model.batch():
        model.part(top_id,top,parent=surfaces,label='Worktop',material='panel.plywood',
                   location=cq.Location(cq.Vector(0,0,height-panel)), color='#dbc797',
                   blank={'size_mm':[width,depth,panel], 'operations':operations})
        model.part(shelf_id,shelf,parent=surfaces,label='Shelf',material='panel.plywood',
                   location=cq.Location(cq.Vector(t,panel,shelf_height)),color='#dbc797',
                   blank={'size_mm':list(shelf_size), 'operations':[{'kind':'panel_cut','finished_size_mm':list(shelf_size)}]})
    for part_id in (top_id,shelf_id):
        model.requirement(part_id+'.blank','stock_fit',[part_id])
    for rail in upper_rails:
        # A native face-area check is independent of the member generator's lengths.
        model.requirement(top_id+'.support.'+rail,'support',[top_id,rail],threshold=1,units='mm2')
    for rail in lower_rails:
        model.requirement(shelf_id+'.support.'+rail,'support',[shelf_id,rail],threshold=1,units='mm2')
    # Named references are evaluated from the completed top geometry.
    bounds = top.val().BoundingBox()
    model.reference(top_id,'front_left',point=(bounds.xmin,bounds.ymin,bounds.zmin))
    model.reference(top_id,'front_right',point=(bounds.xmax,bounds.ymin,bounds.zmin))
    model.reference(top_id,'back_left',point=(bounds.xmin,bounds.ymax,bounds.zmin))
    model.reference(legs[0],'floor',point=(0,0,0))
    model.reference(top_id,'height',point=(0,0,panel))
    model.requirement(object_id+'.width','length',[top_id+':front_left',top_id+':front_right'],threshold=width)
    model.dimension(object_id+'.width',top_id+':front_left',top_id+':front_right',label='Overall width')
    model.dimension(object_id+'.depth',top_id+':front_left',top_id+':back_left',label='Depth')
    model.dimension(object_id+'.height',legs[0]+':floor',top_id+':height',label='Height')
    view_location=location or cq.Location()
    view_up=vector_at(view_location,(0,0,1))
    model.drawing(object_id+'.front', label='Workbench - front elevation', objects=[object_id],
                  dimensions=[object_id+'.width',object_id+'.height'], direction=vector_at(view_location,(0,-1,0)),up=view_up)
    model.drawing(object_id+'.top', label='Workbench - top plan', objects=[object_id],
                  dimensions=[object_id+'.width',object_id+'.depth'], direction=view_up, up=vector_at(view_location,(0,1,0)))
    model.drawing(object_id+'.section',label='Workbench - center section',objects=[object_id],
                  direction=vector_at(view_location,(1,0,0)),up=view_up,
                  section={'origin':point_at(view_location,(width/2,0,0)),'normal':vector_at(view_location,(1,0,0))})
    model.demand(object_id+'.lumber',product_id='lumber.2x4',specification=lumber_spec,
                  object_ids=legs+upper_rails+lower_rails,unit='mm',purchase_unit='board',
                  stock_lengths_mm=[inches(96)],cuts_mm=cuts,kerf_mm=3)
    sheet_width, sheet_depth = inches(96),inches(48)
    panels = [dict(object_id=top_id, origin_mm=[0,0], size_mm=[width,depth], operations=operations,
                   supported_edges={'front':upper_rails[0],'back':upper_rails[1],'left':upper_rails[2],'right':upper_rails[3]}),
              dict(object_id=shelf_id, origin_mm=[0,depth+3],size_mm=list(shelf_size[:2]),
                   supported_edges={'front':lower_rails[0],'back':lower_rails[1]})]
    if max(width,shelf_size[0]) <= sheet_width and depth+3+shelf_size[1] <= sheet_depth:
        sheets = [dict(id=object_id+'.sheet.1',size_mm=[sheet_width,sheet_depth],panels=panels,kerf_mm=3)]
    else:
        # Larger variants use separate identified sheets; oversize panels remain
        # explicit missing detail instead of an area-only cutting layout.
        sheets = [dict(id=f'{object_id}.sheet.{i+1}',size_mm=[sheet_width,sheet_depth],
                       panels=[{**part,'origin_mm':[0,0]}],kerf_mm=3) for i,part in enumerate(panels)]
    unresolved = ['Panel exceeds selected sheet; subdivide and detail its joint.'] if any(
        p['size_mm'][0]>sheet_width or p['size_mm'][1]>sheet_depth for p in panels) else []
    model.demand(object_id+'.plywood',product_id='panel.plywood',specification=plywood_spec,
                  object_ids=[top_id,shelf_id],purchase_unit='sheet',sheets=sheets,unresolved=unresolved)
    connections=[]
    for level, rails in [('upper',upper_rails),('lower',lower_rails)]:
        connection_id=object_id+'.fasten.'+level
        model.connection(connection_id,parts=legs+rails,
            description='Clamp the frame square; predrill and drive two 5 x 80 mm wood screws at each rail end.',
            hardware={'product_id':'screws.5x80','count':len(rails)*4},
            operations=['Predrill using the screw manufacturer pilot-hole guidance.','Keep both screws clear of member edges.'])
        connections.append(connection_id)
    panel_connection=object_id+'.fasten.panels'
    model.connection(panel_connection,parts=[top_id,shelf_id]+upper_rails+lower_rails,
        description='Predrill and fasten panels to the supporting rails with 4 x 40 mm countersunk wood screws.',
        hardware={'product_id':'screws.4x40','count':24})
    model.demand(object_id+'.frame_screws',product_id='screws.5x80',specification={'diameter_mm':5,'length_mm':80,'type':'wood'},
                  object_ids=legs+upper_rails+lower_rails,quantity=(len(upper_rails)+len(lower_rails))*4,pack_size=50,purchase_unit='pack')
    model.demand(object_id+'.panel_screws',product_id='screws.4x40',specification={'diameter_mm':4,'length_mm':40,'type':'countersunk wood'},
                  object_ids=[top_id,shelf_id],quantity=24,pack_size=50,purchase_unit='pack')
    model.step(object_id+'.cut','Cut and label the frame members and panels. Bore the worktop dog hole at the specified offset.',
               parts=legs+upper_rails+lower_rails+[top_id,shelf_id],view=object_id+'.top')
    model.step(object_id+'.frame','Assemble the two leg pairs and rails on a flat surface. Check diagonals before tightening screws.',
               parts=legs+upper_rails+lower_rails,prerequisites=[object_id+'.cut'],connections=connections,view=object_id+'.front')
    model.step(object_id+'.panels','Fit the shelf, then the worktop. Confirm the overhangs and screw only into the named supporting rails.',
               parts=[top_id,shelf_id]+upper_rails+lower_rails,prerequisites=[object_id+'.frame'],
               connections=[panel_connection],view=object_id+'.top',exploded={top_id:[0,0,200],shelf_id:[0,0,100]})
    return dict(id=object_id,legs=legs,upper_rails=upper_rails,lower_rails=lower_rails,top=top_id,shelf=shelf_id)


def rotated_opening(model, *, object_id='opening', width=900, height=2100, angle=30,
                    origin=(0,0,0), mirrored_detail=False):
    model.assembly(object_id,'Rotated opening',location=cq.Location(cq.Vector(*origin),cq.Vector(0,0,1),angle))
    t,depth,header=38,89,140
    parts=[]
    for name,size,offset in [('left_jamb',(t,depth,height),(0,0,0)),
                             ('right_jamb',(t,depth,height),(width+t,0,0)),
                             ('header',(width+2*t,depth,header),(0,0,height))]:
        pid=object_id+'.'+name
        shape=cq.Workplane('XY').box(*size,centered=(False,False,False))
        cut_length=height if name!='header' else width+2*t
        model.part(pid,shape,parent=object_id,location=cq.Location(cq.Vector(*offset)),
                   blank={'size_mm':list(size),'cut_length_mm':cut_length,'operations':[{'kind':'square_cut','finished_length_mm':cut_length}]},
                   material='lumber.38x89' if name!='header' else 'lumber.89x140')
        model.requirement(pid+'.blank','stock_fit',[pid])
        parts.append(pid)
    model.reference(parts[0],'clear_left',point=(t,0,0))
    model.reference(parts[1],'clear_right',point=(0,0,0))
    model.requirement(object_id+'.clear_width','length',[parts[0]+':clear_left',parts[1]+':clear_right'],threshold=width)
    model.requirement(object_id+'.header.left','support',[parts[2],parts[0]],threshold=t*depth,units='mm2')
    model.requirement(object_id+'.header.right','support',[parts[2],parts[1]],threshold=t*depth,units='mm2')
    # The asymmetric, bored corner is mirrored in the solid, never in viewer transforms.
    detail=cq.Workplane('XY').polyline([(0,0),(70,0),(70,25),(25,70),(0,70)]).close().extrude(6)
    detail=detail.cut(cq.Workplane('XY').circle(4).extrude(6).translate((15,15,0)))
    if mirrored_detail:
        detail=detail.mirror('YZ').translate((70,0,0))
    pid=object_id+'.corner_detail'
    profile=[(0,0),(70,0),(70,25),(25,70),(0,70)]
    if mirrored_detail:profile=[(70-x,y) for x,y in profile]
    model.part(pid,detail,parent=object_id,location=cq.Location(cq.Vector(t,0,height+header)),
               material='steel.plate.70x70x6',
               blank={'size_mm':[70,70,6],'operations':[{'kind':'profile_cut','profile_mm':profile},
                   {'kind':'bore','diameter_mm':8,'center_mm':[55 if mirrored_detail else 15,15],'through':True,'axis':'Z'}]},color='#758185')
    model.requirement(pid+'.blank','stock_fit',[pid])
    model.dimension(object_id+'.width',parts[0]+':clear_left',parts[1]+':clear_right',label='Clear opening')
    model.drawing(object_id+'.elevation',objects=[object_id],direction=(math.sin(math.radians(angle)),-math.cos(math.radians(angle)),0),
                  dimensions=[object_id+'.width'])
    model.drawing(object_id+'.corner_plan',label='Corner sample: profile and bore',objects=[pid],direction=(0,0,1),
        up=(-math.sin(math.radians(angle)),math.cos(math.radians(angle)),0),detail_of=object_id+'.elevation')
    for key, ids, section, lengths in [('jambs',parts[:2],[t,depth],[height,height]),
                                      ('header',[parts[2]],[depth,header],[width+2*t])]:
        model.demand(object_id+'.'+key,product_id='lumber.'+'x'.join(map(str,section)),
            specification={'material':'softwood','section_mm':section},object_ids=ids,unit='mm',purchase_unit='board',
            stock_lengths_mm=[2400],cuts_mm=[dict(object_id=part,length_mm=length) for part,length in zip(ids,lengths)],kerf_mm=3)
    model.demand(object_id+'.steel',product_id='steel.plate.70x70x6',specification={'material':'steel','size_mm':[70,70,6]},
                 object_ids=[pid],quantity=1,purchase_unit='each')
    model.connection(object_id+'.joint',parts=parts,
        description='Seat the header on both jamb ends. Clamp square and fasten with two 5 x 80 mm screws into each jamb.',
        hardware={'product_id':'screws.5x80','count':4})
    model.demand(object_id+'.screws',product_id='screws.5x80',specification={'diameter_mm':5,'length_mm':80,'type':'wood'},
                 object_ids=parts,quantity=4,pack_size=50,purchase_unit='pack')
    model.step(object_id+'.assemble','Cut the jambs and header to the listed lengths, label them, and assemble the opening on a flat surface.',
               parts=parts,connections=[object_id+'.joint'],view=object_id+'.elevation')
    model.step(object_id+'.corner','Cut and bore the separate mirrored corner sample using its local blank dimensions; this sample is not a specified structural connector.',
               parts=[pid],prerequisites=[object_id+'.assemble'],view=object_id+'.corner_plan')
    return parts+[pid]


def cut_rafter(*, slope, run, seat=89, thickness=38, height=140):
    """Finished sloped solid in its stock frame, placement, and fabrication data."""
    if not 0 < slope <= 1 or not 0 < seat < run:
        raise ValueError('Use a positive slope up to 1:1 and a bearing seat inside the rafter run.')
    angle=math.atan(slope)
    length=(run+height*math.sin(angle))/math.cos(angle)
    rotation=cq.Location(cq.Vector(0,0,0),cq.Vector(1,0,0),math.degrees(angle))
    blank=cq.Workplane('XY').box(thickness,length,height,centered=(False,False,False)).val()
    stock_world=blank.moved(rotation)
    plumb_window=cq.Workplane('XY').box(thickness,run,run*slope+height/math.cos(angle),centered=(False,False,False)).val()
    rafter=stock_world.intersect(plumb_window)
    # Cut the seat in assembly coordinates, then archive the finished solid
    # in its actual rectangular stock frame for an independent fit query.
    notch=cq.Workplane('XY').box(thickness,seat,seat*slope,centered=(False,False,False))
    rafter=rafter.cut(notch.val()).moved(rotation.inverse)
    fabrication={'size_mm':[thickness,length,height], 'cut_length_mm':length,
                 'operations':[{'kind':'plumb_cut','slope':slope,'horizontal_run_mm':run},
                               {'kind':'birdsmouth','seat_mm':seat,'seat_z_mm':seat*slope,'frame':'assembly',
                                'stock_seat_endpoints_mm':[point_at(rotation.inverse,p) for p in [(0,0,seat*slope),(0,seat,seat*slope)]]}]}
    return rafter,rotation,fabrication


def roof_joint(model, *, object_id='roof_joint', slope=0.5, run=500, seat=89):
    model.assembly(object_id,'Roof bearing detail')
    thickness,height=38,140
    rafter,rotation,fabrication=cut_rafter(slope=slope,run=run,seat=seat)
    length=fabrication['cut_length_mm']
    rafter_id=object_id+'.rafter'
    model.part(rafter_id,rafter,parent=object_id,material='lumber.38x140',location=rotation,
               blank=fabrication)
    plate_id=object_id+'.plate'
    plate=cq.Workplane('XY').box(thickness,seat,38,centered=(False,False,False))
    model.part(plate_id,plate,parent=object_id,location=cq.Location(cq.Vector(0,0,seat*slope-38)),
               material='lumber.38x'+str(seat),blank={'size_mm':[thickness,seat,38],'cut_length_mm':thickness,
                   'operations':[{'kind':'square_cut','finished_length_mm':thickness}]})
    model.requirement(object_id+'.bearing','support',[rafter_id,plate_id],threshold=thickness*seat,units='mm2')
    model.requirement(object_id+'.collision','collision',[rafter_id,plate_id],threshold=0,units='mm3')
    for pid in [rafter_id,plate_id]:
        model.requirement(pid+'.blank','stock_fit',[pid])
    model.reference(rafter_id,'seat_front',point=point_at(rotation.inverse,(0,0,seat*slope)))
    model.reference(rafter_id,'seat_back',point=point_at(rotation.inverse,(0,seat,seat*slope)))
    model.dimension(object_id+'.seat',rafter_id+':seat_front',rafter_id+':seat_back',label='Bearing seat')
    model.drawing(object_id+'.detail',objects=[object_id],direction=(1,0,0),dimensions=[object_id+'.seat'])
    for part,section,cut in [(rafter_id,[thickness,height],length),(plate_id,[38,seat],thickness)]:
        model.demand(part+'.stock',product_id='lumber.'+'x'.join(map(str,section)),
            specification={'material':'softwood','section_mm':section},object_ids=[part],unit='mm',purchase_unit='board',
            stock_lengths_mm=[2400],cuts_mm=[{'object_id':part,'length_mm':cut}],kerf_mm=3)
    model.connection(object_id+'.seat_joint',parts=[rafter_id,plate_id],
        description='Cut the plumb ends and flat seat shown, then seat the rafter fully against the plate. This isolated bearing sample does not specify uplift or lateral restraint.',
        unresolved=['A complete roof needs a separately specified uplift and lateral connection.'])
    model.step(object_id+'.seat_sample','Mark the rafter in its 38 x 140 mm rectangular blank, cut both plumb ends, and make the birdsmouth. Check the full bearing face against the plate.',
               parts=[rafter_id,plate_id],connections=[object_id+'.seat_joint'],view=object_id+'.detail')
    return [rafter_id,plate_id]
