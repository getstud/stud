"""Project-owned workbench example; dimensions are native inches."""
import cadquery as cq
from stud.cad import point_at, vector_at
from stud.construction import imperial_model


def workbench(model, *, object_id='bench', width=72, depth=24,
              height=36, shelf_height=10, dog_hole=(8, 4), location=None):
    imperial_model(model)
    t, b, panel = 1.5, 3.5, .75
    if width <= 2*t or depth <= 2*b or height <= shelf_height + 2*b + panel:
        raise ValueError('Workbench dimensions leave no room for its frame and shelf.')
    model.assembly(object_id, 'Workbench', location=location)
    frame = model.assembly(object_id+'.frame', 'Frame', parent=object_id)
    surfaces = model.assembly(object_id+'.surfaces', 'Top and shelf', parent=object_id)
    cuts, legs, upper_rails, lower_rails = [], [], [], []
    lumber_spec = {'material': 'softwood', 'section': [t, b], 'grade': 'construction'}
    plywood_spec = {'material': 'plywood', 'thickness': panel, 'sheet': [96, 48]}

    def member(key, size, origin, cut_length, group):
        part_id = object_id+'.'+key
        shape = cq.Workplane('XY').box(*size, centered=(False, False, False))
        model.part(part_id, shape, parent=frame, label=key.replace('.', ' ').title(),
                   location=cq.Location(cq.Vector(*origin)), material='lumber.2x4',
                   blank={'size': list(size), 'cut_length': cut_length,
                          'operations': [{'kind': 'square_cut', 'finished_length': cut_length}]})
        model.requirement(part_id+'.blank', 'stock_fit', [part_id], explanation='Finished member fits its stated stock blank.')
        cuts.append({'object_id': part_id, 'length': cut_length})
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
                                      threshold=t*b, units='in2', explanation='Square rail end contacts its leg.')
        for side, x in [('left',0),('right',width-t)]:
            rail = member('rail.upper.'+side, (t,depth-2*b,b), (x,b,height-panel-b), depth-2*b, upper_rails)
            for end in ('front','back'):
                model.requirement(rail+'.'+end+'.contact', 'contact', [rail,f'{object_id}.leg.{side}.{end}'],
                                  threshold=t*b, units='in2', explanation='Side rail bears against the leg face.')

    top_id, shelf_id = object_id+'.top', object_id+'.shelf'
    top = cq.Workplane('XY').box(width,depth,panel,centered=(False,False,False))
    operations = [{'kind':'panel_cut', 'finished_size':[width,depth,panel]}]
    if dog_hole:
        hx, hy = dog_hole
        radius = .375
        if not radius < hx < width-radius or not radius < hy < depth-radius:
            raise ValueError('The deliberate dog hole must remain inside the worktop.')
        boring = cq.Workplane('XY').circle(radius).extrude(panel).translate((hx,hy,0))
        top = top.cut(boring)
        operations.append({'kind':'bore', 'diameter':radius*2, 'center':[hx,hy], 'through':True})
    shelf_size = (width-2*t, depth-panel*2, panel)
    shelf = cq.Workplane('XY').box(*shelf_size,centered=(False,False,False))
    with model.batch():
        model.part(top_id,top,parent=surfaces,label='Worktop',material='panel.plywood',
                   location=cq.Location(cq.Vector(0,0,height-panel)), color='#dbc797',
                   blank={'size':[width,depth,panel], 'operations':operations})
        model.part(shelf_id,shelf,parent=surfaces,label='Shelf',material='panel.plywood',
                   location=cq.Location(cq.Vector(t,panel,shelf_height)),color='#dbc797',
                   blank={'size':list(shelf_size), 'operations':[{'kind':'panel_cut','finished_size':list(shelf_size)}]})
    for part_id in (top_id,shelf_id):
        model.requirement(part_id+'.blank','stock_fit',[part_id])
    for rail in upper_rails:
        # A native face-area check is independent of the member generator's lengths.
        model.requirement(top_id+'.support.'+rail,'support',[top_id,rail],threshold=1,units='in2')
    for rail in lower_rails:
        model.requirement(shelf_id+'.support.'+rail,'support',[shelf_id,rail],threshold=1,units='in2')
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
                  object_ids=legs+upper_rails+lower_rails,unit='in',purchase_unit='board',
                  stock_lengths=[96],cuts=cuts,kerf=.125)
    sheet_width, sheet_depth = 96,48
    panels = [dict(object_id=top_id, origin=[0,0], size=[width,depth], operations=operations,
                   supported_edges={'front':upper_rails[0],'back':upper_rails[1],'left':upper_rails[2],'right':upper_rails[3]}),
              dict(object_id=shelf_id, origin=[0,depth+.125],size=list(shelf_size[:2]),
                   supported_edges={'front':lower_rails[0],'back':lower_rails[1]})]
    if max(width,shelf_size[0]) <= sheet_width and depth+.125+shelf_size[1] <= sheet_depth:
        sheets = [dict(id=object_id+'.sheet.1',size=[sheet_width,sheet_depth],panels=panels,kerf=.125)]
    else:
        # Larger variants use separate identified sheets; oversize panels remain
        # explicit missing detail instead of an area-only cutting layout.
        sheets = [dict(id=f'{object_id}.sheet.{i+1}',size=[sheet_width,sheet_depth],
                       panels=[{**part,'origin':[0,0]}],kerf=.125) for i,part in enumerate(panels)]
    unresolved = ['Panel exceeds selected sheet; subdivide and detail its joint.'] if any(
        p['size'][0]>sheet_width or p['size'][1]>sheet_depth for p in panels) else []
    model.demand(object_id+'.plywood',product_id='panel.plywood',specification=plywood_spec,
                  object_ids=[top_id,shelf_id],purchase_unit='sheet',sheets=sheets,unresolved=unresolved)
    connections=[]
    for level, rails in [('upper',upper_rails),('lower',lower_rails)]:
        connection_id=object_id+'.fasten.'+level
        model.connection(connection_id,parts=legs+rails,
            description='Clamp the frame square; predrill and drive two #10 x 3 in wood screws at each rail end.',
            hardware={'product_id':'screws.no10x3','count':len(rails)*4},
            operations=['Predrill using the screw manufacturer pilot-hole guidance.','Keep both screws clear of member edges.'])
        connections.append(connection_id)
    panel_connection=object_id+'.fasten.panels'
    model.connection(panel_connection,parts=[top_id,shelf_id]+upper_rails+lower_rails,
        description='Predrill and fasten panels to the supporting rails with #8 x 1 1/2 in countersunk wood screws.',
        hardware={'product_id':'screws.no8x1_5','count':24})
    model.demand(object_id+'.frame_screws',product_id='screws.no10x3',specification={'gauge':'#10','length':3,'type':'wood'},
                  object_ids=legs+upper_rails+lower_rails,quantity=(len(upper_rails)+len(lower_rails))*4,pack_size=50,purchase_unit='pack')
    model.demand(object_id+'.panel_screws',product_id='screws.no8x1_5',specification={'gauge':'#8','length':1.5,'type':'countersunk wood'},
                  object_ids=[top_id,shelf_id],quantity=24,pack_size=50,purchase_unit='pack')
    model.step(object_id+'.cut','Cut and label the frame members and panels. Bore the worktop dog hole at the specified offset.',
               parts=legs+upper_rails+lower_rails+[top_id,shelf_id],view=object_id+'.top')
    model.step(object_id+'.frame','Assemble the two leg pairs and rails on a flat surface. Check diagonals before tightening screws.',
               parts=legs+upper_rails+lower_rails,prerequisites=[object_id+'.cut'],connections=connections,view=object_id+'.front')
    model.step(object_id+'.panels','Fit the shelf, then the worktop. Confirm the overhangs and screw only into the named supporting rails.',
               parts=[top_id,shelf_id]+upper_rails+lower_rails,prerequisites=[object_id+'.frame'],
               connections=[panel_connection],view=object_id+'.top',exploded={top_id:[0,0,8],shelf_id:[0,0,4]})
    return dict(id=object_id,legs=legs,upper_rails=upper_rails,lower_rails=lower_rails,top=top_id,shelf=shelf_id)
