"""Repeated framing with physical openings, sheet cuts and stable instance IDs."""
import math

import cadquery as cq

from .cad import inches, point_at, vector_at


def station(value):
    return f'{value:.3f}'.rstrip('0').rstrip('.').replace('.', '_')


def stations(length, spacing, thickness):
    return [('start', 0)] + [('at_'+station(i*spacing), i*spacing-thickness/2)
            for i in range(1, math.ceil(length/spacing)) if i*spacing+thickness/2 <= length-thickness] + [('end', length-thickness)]


def sheet_count(length, stock):
    return math.ceil((length-.01)/stock)


def panel_spans(length, stock, supports):
    """Put seams on real member centers while keeping every blank within stock."""
    boundaries=[0.0];supports=tuple(supports)
    while length-boundaries[-1]>stock+.01:
        choices=[x for x in supports if boundaries[-1]+.01<x<=boundaries[-1]+stock+.01]
        if not choices:raise ValueError('No framing supports a sheet seam within the selected stock width.')
        boundaries.append(max(choices))
    boundaries.append(length)
    return list(zip(boundaries,boundaries[1:]))


def free_spans(length, occupied):
    cursor=0
    for start,end in sorted(occupied):
        start,end=max(0,start),min(length,end)
        if start>cursor+.01:yield cursor,start
        cursor=max(cursor,end)
    if cursor<length-.01:yield cursor,length


def backed_columns(extent, boxes, axis, openings):
    candidates={origin[0]+size[0]/2 for origin,size in boxes.values()}
    for x in sorted(candidates):
        intervals=[(origin[axis],origin[axis]+size[axis]) for origin,size in boxes.values() if origin[0]<=x<=origin[0]+size[0]]
        intervals += [(start,start+length) for left,right,start,length in openings if left<=x<=right]
        if not list(free_spans(extent,intervals)):yield x


def framed_wall(model, *, object_id, length, height=2438.4, depth=89, thickness=38,
                spacing=406.4, openings=(), location=None, sheathing=True, panel_thickness=12.7,
                exceptions=None, parent=None):
    """Local X follows the wall; negative Y is its exterior; Z is vertical.

    Opening x/sill/width/height are clear rough-opening dimensions. Each opening
    owns the framing it displaces and its sheathing cutouts. Exceptions are keyed
    by the stable member key (for example ``stud.at_812_8``), never list position.
    """
    if length < 6*thickness or height < 6*thickness or depth <= 0 or spacing <= thickness:
        raise ValueError('Wall dimensions do not leave room for framing.')
    openings = [dict(opening) for opening in openings]
    seen = set()
    for opening in openings:
        if not opening.get('id') or opening['id'] in seen:
            raise ValueError('Each opening needs its own stable id.')
        seen.add(opening['id'])
        opening.setdefault('sill', 0)
        opening.setdefault('header_depth', 140)
        x, w, sill, h = (opening[k] for k in ('x', 'width', 'sill', 'height'))
        if x < 2*thickness or x+w > length-2*thickness or w <= 0 or h <= 0 or sill < 0:
            raise ValueError('An opening and its jambs must fit inside the wall.')
        if sill and sill < 2*thickness:
            raise ValueError('A window sill needs room above the bottom plate.')
        if sill+h+opening['header_depth'] >= height-2*thickness:
            raise ValueError('An opening header must fit below the top plates.')
    for a, b in zip(sorted(openings, key=lambda o:o['x']), sorted(openings, key=lambda o:o['x'])[1:]):
        if a['x']+a['width']+2*thickness > b['x']-2*thickness:
            raise ValueError('Opening jamb groups overlap.')
    exceptions = dict(exceptions or {})
    used_exceptions = set()
    model.assembly(object_id, object_id.replace('.', ' ').title(), location=location, parent=parent)
    frame = model.assembly(object_id+'.frame', 'Framing', parent=object_id)
    skin = model.assembly(object_id+'.skin', 'Sheathing', parent=object_id)
    parts, cuts, groups, opening_parts, boxes = [], {}, {}, {}, {}

    def board(key, size, origin, cut_length, section=None):
        if min(size) <= .01:
            return None
        part_id = object_id+'.'+key
        shape = cq.Workplane('XY').box(*size, centered=(False,False,False))
        operations = [{'kind':'square_cut', 'finished_length_mm':cut_length}]
        exception = exceptions.get(key)
        if exception:
            used_exceptions.add(key)
            hole = exception.get('bore')
            if set(exception) != {'bore'} or not hole:
                raise ValueError('A member exception currently supports an explicit through-Y bore.')
            x, z, diameter = hole['x'], hole['z'], hole['diameter']
            if not diameter/2 < x < size[0]-diameter/2 or not diameter/2 < z < size[2]-diameter/2:
                raise ValueError('The deliberate bore must remain inside its member.')
            tool = cq.Workplane('XZ').center(x,z).circle(diameter/2).extrude(size[1]+2, both=True)
            shape = shape.cut(tool)
            operations.append({'kind':'bore', 'diameter_mm':diameter, 'center_mm':[x,z], 'through':True, 'axis':'Y'})
        section = section or [thickness, depth]
        product = 'lumber.'+'x'.join(f'{value:g}' for value in section)
        model.part(part_id, shape, parent=frame, label=key.replace('.', ' ').replace('_',' ').title(),
            material=product, location=cq.Location(cq.Vector(*origin)),
            blank={'size_mm':list(size), 'cut_length_mm':cut_length, 'operations':operations})
        model.requirement(part_id+'.blank', 'stock_fit', [part_id])
        parts.append(part_id)
        boxes[part_id]=(list(origin),list(size))
        cuts.setdefault(product, []).append({'object_id':part_id, 'length_mm':cut_length})
        groups[product] = section
        return part_id

    bottom, top, vertical = [], [], []
    with model.batch():
        cursor, previous = 0, 'start'
        for opening in sorted([o for o in openings if not o['sill']], key=lambda o:o['x']):
            piece = board('plate.bottom.'+previous, (opening['x']-cursor,depth,thickness), (cursor,0,0), opening['x']-cursor)
            if piece: bottom.append(piece)
            cursor, previous = opening['x']+opening['width'], 'after_'+opening['id']
        piece = board('plate.bottom.'+previous, (length-cursor,depth,thickness), (cursor,0,0), length-cursor)
        if piece: bottom.append(piece)
        for level in range(2):
            top.append(board('plate.top.'+str(level+1), (length,depth,thickness),
                             (0,0,height-(2-level)*thickness), length))
        for key, x in stations(length, spacing, thickness):
            if any(x+thickness > o['x']-2*thickness+.01 and x < o['x']+o['width']+2*thickness-.01 for o in openings):
                continue
            vertical.append(board('stud.'+key, (thickness,depth,height-3*thickness), (x,0,thickness), height-3*thickness))
        for opening in openings:
            key, x, w, sill, h, hd = (opening[k] for k in ('id','x','width','sill','height','header_depth'))
            ids = {}
            for side, king_x, jack_x in [('left',x-2*thickness,x-thickness),('right',x+w+thickness,x+w)]:
                ids['king.'+side] = board(key+'.king.'+side, (thickness,depth,height-3*thickness),
                                          (king_x,0,thickness), height-3*thickness)
                ids['jack.'+side] = board(key+'.jack.'+side, (thickness,depth,sill+h-thickness),
                                          (jack_x,0,thickness), sill+h-thickness)
            ids['header'] = board(key+'.header', (w+2*thickness,depth,hd), (x-thickness,0,sill+h), w+2*thickness,
                                  section=[depth,hd])
            if sill:
                ids['sill'] = board(key+'.sill', (w,depth,thickness), (x,0,sill-thickness), w)
            for at_key, at_x in stations(length, spacing, thickness):
                if not x <= at_x or at_x+thickness > x+w:
                    continue
                above = height-2*thickness-(sill+h+hd)
                ids['above.'+at_key] = board(key+'.above.'+at_key, (thickness,depth,above), (at_x,0,sill+h+hd), above)
                if sill:
                    below = sill-2*thickness
                    ids['below.'+at_key] = board(key+'.below.'+at_key, (thickness,depth,below), (at_x,0,thickness), below)
            opening_parts[key] = ids
            for side in ('left','right'):
                model.requirement(object_id+'.'+key+'.bearing.'+side, 'support',
                    [ids['header'],ids['jack.'+side]], threshold=depth*thickness-.01, units='mm2')
            left = model.reference(ids['jack.left'], 'clear', point=(thickness,0,sill-thickness))
            right = model.reference(ids['jack.right'], 'clear', point=(0,0,sill-thickness))
            model.dimension(object_id+'.'+key+'.width', left, right, label=key+' clear width')
            model.requirement(object_id+'.'+key+'.clear_width', 'length', [left,right], threshold=w)
            lower = model.reference(ids['jack.left'], 'clear_bottom', point=(thickness,0,sill-thickness))
            upper = model.reference(ids['jack.left'], 'clear_top', point=(thickness,0,sill+h-thickness))
            model.dimension(object_id+'.'+key+'.height', lower, upper, label=key+' clear height')
    if set(exceptions)-used_exceptions:
        raise ValueError('Deliberate member exceptions no longer resolve: '+', '.join(sorted(set(exceptions)-used_exceptions)))
    panel_ids, sheets = [], []
    if sheathing:
        sw, sh, gap = inches(48), inches(96), 3
        columns=panel_spans(length,sw,backed_columns(height,boxes,2,[(o['x'],o['x']+o['width'],o['sill'],o['height']) for o in openings]))
        # Backing at every horizontal sheet seam is an actual framed member.
        seam_members = []
        for row in range(1, sheet_count(height,sh)):
            z = row*sh-thickness/2
            occupied=[(origin[0],origin[0]+size[0]) for origin,size in boxes.values() if origin[2]<z+thickness and origin[2]+size[2]>z]
            occupied += [(o['x'],o['x']+o['width']) for o in openings if o['sill']<z+thickness and o['sill']+o['height']>z]
            for start,end in free_spans(length,occupied):
                seam_members.append(board(f'blocking.{row}.at_{station(start)}', (end-start,depth,thickness), (start,0,z), end-start))
        with model.batch():
            for col,(x,last) in enumerate(columns):
                for row in range(sheet_count(height,sh)):
                    z = row*sh
                    width = last-x-(gap if last < length-.01 else 0)
                    high = min(sh,height-z)-(gap if z+sh < height-.01 else 0)
                    pid = object_id+f'.panel.{col}.{row}'
                    shape = cq.Workplane('XY').box(width,panel_thickness,high,centered=(False,False,False))
                    operations = [{'kind':'panel_cut','finished_size_mm':[width,high,panel_thickness]}]
                    for opening in openings:
                        ox, oz, ow, oh = opening['x']-x, opening['sill']-z, opening['width'], opening['height']
                        if ox < width and ox+ow > 0 and oz < high and oz+oh > 0:
                            tool = cq.Workplane('XY').box(ow,panel_thickness+2,oh,centered=(False,False,False)).translate((ox,-1,oz))
                            shape = shape.cut(tool)
                            operations.append({'kind':'rectangular_opening','origin_mm':[max(ox,0),max(oz,0)],
                                'size_mm':[min(ox+ow,width)-max(ox,0),min(oz+oh,high)-max(oz,0)],'opening_id':opening['id']})
                    if not shape.val().Solids():
                        continue
                    model.part(pid,shape,parent=skin,label=f'Sheathing {col+1}.{row+1}',material='panel.plywood',color='#c8b183',
                        location=cq.Location(cq.Vector(x,-panel_thickness,z)),
                        blank={'size_mm':[width,panel_thickness,high],'panel_axes':[0,2], 'operations':operations})
                    model.requirement(pid+'.blank','stock_fit',[pid])
                    supports = [part for part in parts if model.shapes[pid]['world'].distance(model.shapes[part]['world']) < .001]
                    # These references identify actual framing behind the sheet;
                    # packet preflight separately checks the sheet and joint data.
                    supported_edges = {'framing':supports}
                    for opening in openings:
                        supported_edges['opening.'+opening['id']] = list(opening_parts[opening['id']].values())
                    model.requirement(pid+'.edge_backing','panel_edge_support',[pid]+supports,threshold=0,
                        direction_local=[0,1,0],explanation='Every actual sheathing edge and opening cut has continuous framing behind it.')
                    sheets.append({'id':pid+'.sheet','size_mm':[sw,sh], 'kerf_mm':3,
                        'panels':[{'object_id':pid,'origin_mm':[0,0],'size_mm':[width,high], 'operations':operations,
                                   'supported_edges':supported_edges,'edge_requirement':pid+'.edge_backing'}],
                        'joints':[{'axis':'X','at_mm':x,'gap_mm':gap,'support_ids':supports}] if col else []})
                    panel_ids.append(pid)
        model.demand(object_id+'.sheathing',product_id='panel.plywood',
            specification={'material':'plywood','thickness_mm':panel_thickness,'sheet_mm':[sw,sh]},
            object_ids=panel_ids,purchase_unit='sheet',sheets=sheets)
    for product, rows in cuts.items():
        longest=max(row['length_mm'] for row in rows)
        lengths=[2438.4,3048,3657.6,4876.8]
        model.demand(object_id+'.'+product,product_id=product,specification={'material':'softwood','section_mm':groups[product]},
            object_ids=[row['object_id'] for row in rows],unit='mm',purchase_unit='board',
            stock_lengths_mm=lengths,cuts_mm=rows,kerf_mm=3,
            unresolved=[] if longest<=max(lengths)+.01 else ['A member exceeds the supported stock lengths.'])
    frame_connection = object_id+'.fasten.frame'
    frame_screws=4*sum('.plate.' not in part for part in parts)+2*math.ceil(length/spacing)
    model.connection(frame_connection,parts=parts,
        description='Lay out the marked stations and rough openings. Clamp the frame square. Predrill and use two 5 x 80 mm wood screws at each member end; fasten the second top plate at 406 mm centers.',
        hardware={'product_id':'screws.5x80','count':frame_screws})
    model.demand(object_id+'.frame_screws',product_id='screws.5x80',specification={'diameter_mm':5,'length_mm':80,'type':'wood'},
                 object_ids=parts,quantity=frame_screws,pack_size=50,purchase_unit='pack')
    skin_connection = object_id+'.fasten.skin'
    if panel_ids:
        count=sum(math.ceil((sheet['panels'][0]['size_mm'][0]+sheet['panels'][0]['size_mm'][1])*2/150)+
                  math.ceil(sheet['panels'][0]['size_mm'][0]/spacing)*math.ceil(sheet['panels'][0]['size_mm'][1]/300) for sheet in sheets)
        model.connection(skin_connection,parts=parts+panel_ids,
            description='Fit the numbered sheets with 3 mm joints centered on framing. Transfer each rough opening from the frame before cutting. Predrill and fasten with 4 x 40 mm wood screws at 150 mm along supported edges and 300 mm on intermediate framing.',
            hardware={'product_id':'screws.4x40','count':count})
        model.demand(object_id+'.skin_screws',product_id='screws.4x40',specification={'diameter_mm':4,'length_mm':40,'type':'countersunk wood'},
                     object_ids=panel_ids,quantity=count,pack_size=50,purchase_unit='pack')
    a=model.reference(top[-1],'start',point=(0,0,thickness))
    b=model.reference(top[-1],'end',point=(length,0,thickness))
    bottom_ref=model.reference(bottom[0],'floor',point=(0,0,0))
    model.dimension(object_id+'.length',a,b,label='Wall length')
    model.dimension(object_id+'.height',bottom_ref,a,label='Wall height')
    model.requirement(object_id+'.length','length',[a,b],threshold=length)
    world=model.shapes[top[-1]]['location']
    direction=vector_at(world,(0,-1,0));up=vector_at(world,(0,0,1))
    dimensions=[object_id+'.length',object_id+'.height']+[object_id+'.'+o['id']+'.'+axis for o in openings for axis in ('width','height')]
    model.drawing(object_id+'.elevation',label=object_id.replace('.',' ').title()+' framing elevation',objects=[frame],
                  direction=direction,up=up,dimensions=dimensions)
    model.drawing(object_id+'.sheets',label=object_id.replace('.',' ').title()+' sheathing',objects=panel_ids or [frame],
                  direction=direction,up=up,dimensions=[object_id+'.length',object_id+'.height'])
    model.step(object_id+'.frame','Cut and label each framing member. Set out the rough openings and member stations, assemble flat, then check both diagonals.',
               parts=parts,connections=[frame_connection],view=object_id+'.elevation')
    if panel_ids:
        model.step(object_id+'.skin','Attach the numbered sheathing panels. Preserve the deliberate opening cuts and leave the specified panel joints.',
                   parts=panel_ids,connections=[skin_connection],prerequisites=[object_id+'.frame'],view=object_id+'.sheets',
                   exploded={pid:[0,-150,0] for pid in panel_ids})
    return dict(id=object_id,frame=frame,parts=parts,panels=panel_ids,openings=opening_parts,top=top,bottom=bottom)


def floor_frame(model, *, object_id, length=3048, depth=2438.4, joist_height=140,
                spacing=406.4, location=None, stair_opening=None, parent=None):
    """A rimmed platform with a physical stair opening and supported sheet seams."""
    t, panel = 38, 19.05
    if min(length,depth) <= 4*t:
        raise ValueError('The floor needs room inside its perimeter rims.')
    model.assembly(object_id,'Floor platform',location=location,parent=parent)
    parts, cuts, boxes = [], [], {}
    def member(key,size,origin,cut_length):
        pid=object_id+'.'+key
        model.part(pid,cq.Workplane('XY').box(*size,centered=(False,False,False)),parent=object_id,
                   label=key.replace('.',' ').title(),location=cq.Location(cq.Vector(*origin)),material=f'lumber.38x{joist_height:g}',
                   blank={'size_mm':list(size),'cut_length_mm':cut_length,'operations':[{'kind':'square_cut','finished_length_mm':cut_length}]})
        model.requirement(pid+'.blank','stock_fit',[pid]);parts.append(pid);cuts.append({'object_id':pid,'length_mm':cut_length})
        boxes[pid]=(list(origin),list(size))
        return pid
    joists=[]
    with model.batch():
        front=member('rim.front',(length,t,joist_height),(0,0,0),length)
        back=member('rim.back',(length,t,joist_height),(0,depth-t,0),length)
        for key,x in stations(length,spacing,t):
            spans=[(t,depth-t,'full')]
            if stair_opening:
                ox,oy,ow,oh=(stair_opening[k] for k in ('x','y','width','depth'))
                if min(ox,oy)<2*t or ox+ow>length-2*t or oy+oh>depth-2*t:
                    raise ValueError('The stair opening must fit inside the floor rim.')
                if x+t > ox-t and x < ox+ow+t:
                    spans=[(t,oy-t,'before'),(oy+oh+t,depth-t,'after')]
            for start,end,span in spans:
                if end<=start:continue
                pid=member('joist.'+key+'.'+span,(t,end-start,joist_height),(x,start,0),end-start)
                joists.append(pid)
                for rim in ([front] if span=='before' else [back] if span=='after' else [front,back]):
                    model.requirement(pid+'.end.'+rim,'contact',[pid,rim],threshold=t*joist_height-.01,units='mm2')
        if stair_opening:
            for side,x in [('left',ox-t),('right',ox+ow)]:
                member('stair.trimmer.'+side,(t,oh+2*t,joist_height),(x,oy-t,0),oh+2*t)
            for side,y in [('front',oy-t),('back',oy+oh)]:
                member('stair.header.'+side,(ow,t,joist_height),(ox,y,0),ow)
    # Sheet joints run over joists at multiples of 48 inches. Deck rows beyond
    # 8 feet have solid blocking at the butt seam between neighboring joists.
    sw,sh,gap=inches(48),inches(96),3
    columns=panel_spans(length,sw,backed_columns(depth,boxes,1,[(ox,ox+ow,oy,oh)] if stair_opening else []))
    for row in range(1,sheet_count(depth,sh)):
        y=row*sh-t/2
        occupied=[(origin[0],origin[0]+size[0]) for origin,size in boxes.values() if origin[1]<y+t and origin[1]+size[1]>y]
        if stair_opening and oy<y+t and oy+oh>y:occupied.append((ox,ox+ow))
        for start,end in free_spans(length,occupied):
            member(f'blocking.{row}.at_{station(start)}',(end-start,t,joist_height),(start,y,0),end-start)
    panels,sheets=[],[]
    with model.batch():
        for col,(x,last) in enumerate(columns):
            for row in range(sheet_count(depth,sh)):
                y=row*sh;w=last-x-(gap if last<length-.01 else 0);h=min(sh,depth-y)-(gap if y+sh<depth-.01 else 0)
                pid=object_id+f'.deck.{col}.{row}'
                shape=cq.Workplane('XY').box(w,h,panel,centered=(False,False,False))
                operations=[{'kind':'panel_cut','finished_size_mm':[w,h,panel]}]
                if stair_opening and x<ox+ow and x+w>ox and y<oy+oh and y+h>oy:
                    shape=shape.cut(cq.Workplane('XY').box(ow,oh,panel+2,centered=(False,False,False)).translate((ox-x,oy-y,-1)))
                    operations.append({'kind':'rectangular_opening','origin_mm':[max(ox-x,0),max(oy-y,0)],
                        'size_mm':[min(ox+ow-x,w)-max(ox-x,0),min(oy+oh-y,h)-max(oy-y,0)],'opening_id':'stair'})
                if not shape.val().Solids():continue
                model.part(pid,shape,parent=object_id,label=f'Floor sheet {col+1}.{row+1}',material='panel.floor',color='#b99972',
                    location=cq.Location(cq.Vector(x,y,joist_height)),blank={'size_mm':[w,h,panel],'operations':operations})
                model.requirement(pid+'.blank','stock_fit',[pid]);panels.append(pid)
                supports=[part for part in parts if model.shapes[pid]['world'].distance(model.shapes[part]['world'])<.001]
                model.requirement(pid+'.edge_backing','panel_edge_support',[pid]+supports,threshold=0,direction_local=[0,0,-1],
                    explanation='Every actual deck edge and stair cut has continuous framing behind it.')
                sheets.append(dict(id=pid+'.sheet',size_mm=[sw,sh],kerf_mm=3,panels=[dict(object_id=pid,origin_mm=[0,0],size_mm=[w,h],
                    operations=operations,supported_edges={'framing':supports},edge_requirement=pid+'.edge_backing')]))
    model.demand(object_id+'.lumber',product_id=f'lumber.38x{joist_height:g}',specification={'material':'softwood','section_mm':[t,joist_height]},
        object_ids=parts,unit='mm',purchase_unit='board',stock_lengths_mm=[2438.4,3048,3657.6,4876.8,6096],cuts_mm=cuts,kerf_mm=3)
    model.demand(object_id+'.decking',product_id='panel.floor',specification={'material':'plywood','thickness_mm':panel,'sheet_mm':[sw,sh]},
                 object_ids=panels,purchase_unit='sheet',sheets=sheets)
    model.connection(object_id+'.frame.joints',parts=parts,description='Assemble the rims and joists on a level bearing surface. Predrill and fasten each joist end with two 6 x 100 mm wood screws. Frame and check the stair opening before decking.',
                     hardware={'product_id':'screws.6x100','count':len(joists)*4})
    model.connection(object_id+'.deck.joints',parts=parts+panels,description='Glue and screw the numbered floor panels to their named framing supports, with 3 mm sheet gaps and 4 x 50 mm screws at 150 mm edges and 300 mm intermediate supports.',
                     hardware={'product_id':'screws.4x50','count':len(panels)*60})
    for product,count,length_,scope in [('screws.6x100',len(joists)*4,100,parts),('screws.4x50',len(panels)*60,50,panels)]:
        model.demand(object_id+'.'+product,product_id=product,specification={'diameter_mm':6 if length_==100 else 4,'length_mm':length_,'type':'wood'},
                     object_ids=scope,quantity=count,purchase_unit='pack',pack_size=50)
    a=model.reference(front,'origin',point=(0,0,0));b=model.reference(front,'end',point=(length,0,0));c=model.reference(back,'back',point=(0,t,0))
    model.dimension(object_id+'.length',a,b,label='Floor length');model.dimension(object_id+'.depth',a,c,label='Floor depth')
    world=model.shapes[front]['location']
    model.drawing(object_id+'.plan',label='Floor framing plan',objects=parts,direction=vector_at(world,(0,0,1)),
        up=vector_at(world,(0,1,0)),dimensions=[object_id+'.length',object_id+'.depth'])
    model.step(object_id+'.frame','Set and square the rims, then fasten the joists and seam blocking. Keep the stair opening clear where specified.',parts=parts,connections=[object_id+'.frame.joints'],view=object_id+'.plan')
    model.step(object_id+'.deck','Fit and fasten the numbered deck sheets, checking the seam supports and cutting the stair opening before use.',parts=panels,connections=[object_id+'.deck.joints'],prerequisites=[object_id+'.frame'],view=object_id+'.plan',exploded={pid:[0,0,150] for pid in panels})
    return dict(id=object_id,parts=parts,panels=panels,joists=joists,top=joist_height+panel)


def gable_roof(model, *, object_id, length, depth, wall_top, slope=.5, spacing=406.4,
               bearing_parts=None, end_bearing_parts=None, parent=None, location=None,
               gable_ends=('left','right')):
    """A paired rafter roof with true stock frames, ties, blocking and sheathing."""
    from .construction import cut_rafter
    t,h,seat,panel=38,140,89,12.7
    run=depth/2-t/2
    rafter_shape,rotation,blank=cut_rafter(slope=slope,run=run,seat=seat)
    angle=math.atan(slope);cosine=math.cos(angle);top_rise=h/cosine
    if set(gable_ends)-{'left','right'}:
        raise ValueError('Gable sheathing ends must be left or right.')
    model.assembly(object_id,'Gable roof',parent=parent,
        location=(location or cq.Location())*cq.Location(cq.Vector(0,0,wall_top-seat*slope)))
    parts,panels,cuts,sections,sheets=[],[],{},{},[]
    rafters={'front':[],'back':[]};blocks={'front':[],'back':[]};ties=[]
    stations_=stations(length,spacing,t)
    mirror=cq.Location(cq.Vector(0,0,0),cq.Vector(0,0,1),180)
    def register(key,shape,location,fabrication,section,label=None):
        pid=object_id+'.'+key;product='lumber.'+'x'.join(f'{v:g}' for v in section)
        model.part(pid,shape,parent=object_id,label=label or key.replace('.',' ').title(),material=product,
                   location=location,blank=fabrication)
        model.requirement(pid+'.blank','stock_fit',[pid]);parts.append(pid)
        cuts.setdefault(product,[]).append({'object_id':pid,'length_mm':fabrication['cut_length_mm']});sections[product]=section
        return pid
    ridge_bottom=run*slope+top_rise-184
    with model.batch():
        ridge=register('ridge',cq.Workplane('XY').box(length,t,184,centered=(False,False,False)),
            cq.Location(cq.Vector(0,run,ridge_bottom)),
            {'size_mm':[length,t,184],'cut_length_mm':length,'operations':[{'kind':'square_cut','finished_length_mm':length}]},[t,184])
        for key,x in stations_:
            for side,place in [('front',cq.Location(cq.Vector(x,0,0))),('back',cq.Location(cq.Vector(x+t,depth,0))*mirror)]:
                pid=register('rafter.'+side+'.'+key,rafter_shape,place*rotation,blank,[t,h])
                rafters[side].append(pid)
                model.requirement(pid+'.ridge','contact',[pid,ridge],threshold=1,units='mm2')
                if bearing_parts and bearing_parts.get(side):
                    model.requirement(pid+'.bearing','support',[pid,bearing_parts[side]],threshold=t*seat-.01,units='mm2')
            if key in ('start','end'):
                continue
            tie_x=x+t
            tie=register('tie.'+key,cq.Workplane('XY').box(t,depth,89,centered=(False,False,False)),
                cq.Location(cq.Vector(tie_x,0,seat*slope)),
                {'size_mm':[t,depth,89],'cut_length_mm':depth,'operations':[{'kind':'square_cut','finished_length_mm':depth}]},[t,89])
            ties.append(tie)
            for side in ('front','back'):
                model.requirement(tie+'.'+side,'contact',[tie,rafters[side][-1]],threshold=1,units='mm2')
        for index,((key,x),(_,next_x)) in enumerate(zip(stations_,stations_[1:])):
            clear=next_x-x-t
            if clear <= 0:continue
            for side in ('front','back'):
                for end,y in [('eave',0),('ridge',run-t)]:
                    profile=[(0,0),(t,0),(t,89+t*slope),(0,89)]
                    shape=cq.Workplane('YZ').polyline(profile).close().extrude(clear)
                    origin=(x+t,y,y*slope+top_rise-89)
                    operations=[{'kind':'beveled_edge','slope':slope,'low_height_mm':89,'high_height_mm':89+t*slope}]
                    if end=='eave' and key not in ('start','end'):
                        notch_height=seat*slope+89-origin[2]
                        notch_x=0 if side=='front' else clear-t
                        shape=shape.cut(cq.Workplane('XY').box(t,t,notch_height,centered=(False,False,False)).translate((notch_x,0,0)))
                        operations.append({'kind':'housing','origin_mm':[notch_x,0,0],'size_mm':[t,t,notch_height],
                                           'description':'Cut the underside housing to clear the adjacent rafter tie.'})
                    place=cq.Location(cq.Vector(*origin)) if side=='front' else cq.Location(cq.Vector(x+next_x-x,depth-y,y*slope+top_rise-89))*mirror
                    pid=register(f'blocking.{side}.{end}.{key}',shape,place,
                        {'size_mm':[clear,t,h],'cut_length_mm':clear,
                         'operations':operations},[t,h])
                    blocks[side].append(pid)
    # The ridge is supported by the actual center posts at each gable. Other
    # posts are clipped to the underside of their neighboring sloped rafters.
    gable_posts={'left':[],'right':[]}
    center_y=depth/2-t/2
    candidates=[(key,y) for key,y in stations(depth,spacing,t) if y>seat and y+t<depth-seat and abs(y-center_y)>t]
    candidates.append(('ridge',center_y))
    with model.batch():
        for end,x in [('left',0),('right',length-seat)]:
            for key,y in candidates:
                if key=='ridge':lo=hi=ridge_bottom-seat*slope
                else:lo,hi=[min(at,depth-at)*slope-seat*slope for at in (y,y+t)]
                if min(lo,hi)<=0:continue
                post_shape=cq.Workplane('YZ').polyline([(0,0),(t,0),(t,hi),(0,lo)]).close().extrude(seat)
                pid=register(f'gable.{end}.{key}',post_shape,cq.Location(cq.Vector(x,y,seat*slope)),
                    {'size_mm':[seat,t,max(lo,hi)],'cut_length_mm':max(lo,hi),
                     'operations':[{'kind':'beveled_end','low_length_mm':lo,'high_length_mm':hi}]},[t,seat])
                gable_posts[end].append(pid)
                if key=='ridge':model.requirement(pid+'.ridge','support',[ridge,pid],threshold=seat*t-.01,units='mm2')
                if end_bearing_parts and end_bearing_parts.get(end):
                    model.requirement(pid+'.base','support',[pid,end_bearing_parts[end]],threshold=seat*t-.01,units='mm2')
            occupied=[(at,at+t) for _,at in candidates]+[(0,seat),(depth-seat,depth)]
            for start,end_at in free_spans(depth,occupied):
                span=end_at-start
                lo,hi=[max(0,min(t,min(at,depth-at)*slope-seat*slope)) for at in (start,end_at)]
                outline=[(0,0),(span,0),(span,hi),(0,lo)]
                if lo<1e-7:outline.pop()
                if hi<1e-7:outline.pop(2)
                shape=cq.Workplane('YZ').polyline(outline).close().extrude(seat)
                pid=register(f'gable.{end}.base.at_{station(start)}',shape,cq.Location(cq.Vector(x,start,seat*slope)),
                    {'size_mm':[seat,span,t],'cut_length_mm':span,'operations':[{'kind':'profile_cut','profile_mm':outline,
                        'description':'Cut the base backing outline on the local Y-Z face.'}]},[t,seat])
                gable_posts[end].append(pid)
    layouts=[]
    with model.batch():
        for side in ('front','back'):
            for index,((key,x),(_,next_x)) in enumerate(zip(stations_,stations_[1:])):
                first=0 if index==0 else x+t/2+1.5
                last=length if index==len(stations_)-2 else next_x+t/2-1.5
                width=last-first;sloped_length=run/cosine
                shape=cq.Workplane('XY').box(width,sloped_length,panel,centered=(False,False,False))
                place=cq.Location(cq.Vector(first,0,0))*rotation*cq.Location(cq.Vector(0,h*math.tan(angle),h))
                if side=='back':place=cq.Location(cq.Vector(last,depth,0))*mirror*rotation*cq.Location(cq.Vector(0,h*math.tan(angle),h))
                pid=object_id+f'.deck.{side}.{key}'
                operations=[{'kind':'panel_cut','finished_size_mm':[width,sloped_length,panel]}]
                model.part(pid,shape,parent=object_id,label=f'{side.title()} roof panel {index+1}',material='panel.roof',color='#cdb68e',
                    location=place,blank={'size_mm':[width,sloped_length,panel],'operations':operations})
                model.requirement(pid+'.blank','stock_fit',[pid]);panels.append(pid)
                supports=rafters[side][index:index+2]+blocks[side][2*index:2*index+2]
                for support in supports:model.requirement(pid+'.support.'+support,'support',[pid,support],threshold=1,units='mm2')
                model.requirement(pid+'.edge_backing','panel_edge_support',[pid]+supports,threshold=0,direction_local=[0,0,-1],
                    explanation='All four edges of this roof panel have continuous opposing contact with its rafters and blocking.')
                layouts.append(dict(object_id=pid,size_mm=[width,sloped_length],operations=operations,
                                    supported_edges={'left':supports[0],'right':supports[1],'eave':supports[2],'ridge':supports[3]},edge_requirement=pid+'.edge_backing'))
    # Each stock sheet has concrete, nonoverlapping cuts. Small bay panels can
    # share a sheet; this is explicit packing, not area converted to sheet count.
    sw,sh=inches(48),inches(96)
    for layout in layouts:
        fit=next((sheet for sheet in sheets if sheet['_x']+layout['size_mm'][0]<=sw+.01 and layout['size_mm'][1]<=sh+.01),None)
        if fit is None:
            fit={'id':object_id+f'.roof.sheet.{len(sheets)+1}','size_mm':[sw,sh],'kerf_mm':3,'panels':[],'_x':0}
            sheets.append(fit)
        fit['panels'].append(dict(**layout,origin_mm=[fit['_x'],0]));fit['_x']+=layout['size_mm'][0]+3
    for sheet in sheets:sheet.pop('_x')
    model.demand(object_id+'.deck',product_id='panel.roof',specification={'material':'plywood','thickness_mm':panel,'sheet_mm':[sw,sh]},
                 object_ids=panels,purchase_unit='sheet',sheets=sheets,
                 unresolved=['Roof panels exceed the selected sheet length. Subdivide with supported joints.'] if run/cosine>sh+.01 else [])
    # Gable panels use a clipped elevation profile, including the rafter depth.
    # Their actual blank frames and polygon cuts are retained in the sheet list.
    gable_panels=[];gable_sheets=[]
    peak=run*slope+top_rise-seat*slope
    profile=[(0,0),(depth,0),(depth,top_rise-seat*slope),(depth-run,peak),(run,peak),(0,top_rise-seat*slope)]
    full=cq.Workplane('YZ').polyline(profile).close().extrude(panel).val()
    with model.batch():
        for end,x in [('left',-panel),('right',length)]:
            if end not in gable_ends:continue
            for index,(y,last) in enumerate(panel_spans(depth,sw,[at+t/2 for _,at in candidates])):
                w=last-y-(3 if last<depth-.01 else 0)
                clip=cq.Workplane('XY').box(panel,w,peak,centered=(False,False,False)).translate((0,y,0)).val()
                shape=full.intersect(clip).moved(cq.Location(cq.Vector(0,-y,0)))
                bounds=shape.BoundingBox();high=bounds.zmax
                pid=object_id+f'.gable.panel.{end}.{index}'
                top_at=lambda at:min(at,depth-at,run)*slope+top_rise-seat*slope
                outline=[[0,0],[w,0],[w,top_at(y+w)]]
                for at in (depth-run,run):
                    if y<at<y+w:outline.append([at-y,peak])
                outline.append([0,top_at(y)])
                operations=[{'kind':'profile_cut','profile_mm':outline,
                             'description':'Transfer the gable outline from the elevation; cut the sloped top to fit the roof underside.'}]
                model.part(pid,shape,parent=object_id,label=f'{end.title()} gable panel {index+1}',material='panel.plywood',color='#c8b183',
                    location=cq.Location(cq.Vector(x,y,seat*slope)),blank={'size_mm':[panel,w,high],'panel_axes':[1,2],'operations':operations})
                model.requirement(pid+'.blank','stock_fit',[pid]);gable_panels.append(pid)
                supports=gable_posts[end]+[ridge]+[rafters[side][0 if end=='left' else -1] for side in ('front','back')]
                if end_bearing_parts and end_bearing_parts.get(end):supports.append(end_bearing_parts[end])
                supports+=list((bearing_parts or {}).values())
                model.requirement(pid+'.edge_backing','panel_edge_support',[pid]+supports,threshold=0,
                    direction_local=[1 if end=='left' else -1,0,0],explanation='The gable profile and sheet seams have continuous framing behind them.')
                gable_sheets.append(dict(id=pid+'.sheet',size_mm=[sw,sh],kerf_mm=3,panels=[dict(object_id=pid,origin_mm=[0,0],size_mm=[w,high],
                    operations=operations,supported_edges={'framing':supports},edge_requirement=pid+'.edge_backing')]))
    if gable_panels:
        model.demand(object_id+'.gable.panels',product_id='panel.plywood',specification={'material':'plywood','thickness_mm':panel,'sheet_mm':[sw,sh]},
                     object_ids=gable_panels,purchase_unit='sheet',sheets=gable_sheets)
    for product,rows in cuts.items():
        model.demand(object_id+'.'+product,product_id=product,specification={'material':'softwood','section_mm':sections[product]},
            object_ids=[r['object_id'] for r in rows],cuts_mm=rows,unit='mm',purchase_unit='board',
            stock_lengths_mm=[2438.4,3048,3657.6,4876.8],kerf_mm=3)
    frame_connection=object_id+'.connections.frame';skin_connection=object_id+'.connections.skin'
    model.connection(frame_connection,parts=parts,description='Set the gable posts and ridge, then install matching rafter pairs with full seats on the top plates. Fasten each rafter tie to both rafter sides with three 6 x 100 mm wood screws. Predrill and screw the end blocking into the rafters.',
        hardware={'product_id':'screws.6x100','count':len(ties)*6+sum(map(len,blocks.values()))*4},
        unresolved=['Specify rated rafter-to-wall uplift connections for the site before construction.'])
    model.connection(skin_connection,parts=parts+panels+gable_panels,description='Install numbered roof and gable panels on the named framing. Leave 3 mm sheet joints. Use 4 x 40 mm screws at 150 mm around supported edges and 300 mm on intermediate framing.',
        hardware={'product_id':'screws.4x40','count':60*(len(panels)+len(gable_panels))})
    for product,count,diameter,length_ in [('screws.6x100',len(ties)*6+sum(map(len,blocks.values()))*4,6,100),
                                         ('screws.4x40',60*(len(panels)+len(gable_panels)),4,40)]:
        model.demand(object_id+'.'+product,product_id=product,specification={'diameter_mm':diameter,'length_mm':length_,'type':'wood'},
                     object_ids=parts+panels+gable_panels,quantity=count,purchase_unit='pack',pack_size=50)
    a=model.reference(ridge,'start',point=(0,0,184));b=model.reference(ridge,'end',point=(length,0,184))
    model.dimension(object_id+'.ridge_length',a,b,label='Ridge length')
    world=model._parent_location(object_id)
    model.drawing(object_id+'.plan',label='Roof framing plan',objects=parts,direction=vector_at(world,(0,0,1)),up=vector_at(world,(0,1,0)),dimensions=[object_id+'.ridge_length'])
    end_scope=gable_posts['left']+[ridge,rafters['front'][0],rafters['back'][0]]+[p for p in gable_panels if '.left.' in p]
    model.drawing(object_id+'.end',label='Gable roof elevation and bearing',objects=end_scope,direction=vector_at(world,(1,0,0)),up=vector_at(world,(0,0,1)),dimensions=[])
    detail_parts=([rafters['front'][1],ties[0]] if ties else [rafters['front'][0]])+([bearing_parts['front']] if bearing_parts and bearing_parts.get('front') else [])
    seat_a=model.reference(rafters['front'][1 if ties else 0],'seat_start',point=blank['operations'][1]['stock_seat_endpoints_mm'][0])
    seat_b=model.reference(rafters['front'][1 if ties else 0],'seat_end',point=blank['operations'][1]['stock_seat_endpoints_mm'][1])
    model.dimension(object_id+'.seat_width',seat_a,seat_b,label='Horizontal bearing seat')
    # Crop coordinates live in the projected view plane, including translation
    # and every parent placement. Its horizontal basis is local +Y.
    right=cq.Vector(*vector_at(world,(0,1,0)));up=cq.Vector(*vector_at(world,(0,0,1)))
    datum=cq.Vector(*point_at(world,(0,0,seat*slope)))
    cx,cy=datum.dot(right),datum.dot(up)
    model.drawing(object_id+'.bearing_detail',label='Rafter seat and tie detail',objects=detail_parts,direction=vector_at(world,(1,0,0)),up=up.toTuple(),
        dimensions=[object_id+'.seat_width'],detail_of=object_id+'.end',crop_mm=[cx-20,cy-60,cx+seat+170,cy+220])
    model.step(object_id+'.frame','Label and pair the rafters. Erect the gable posts and ridge, then attach the rafters, ties and blocking. Verify full bearing before closing the roof.',parts=parts,connections=[frame_connection],view=object_id+'.end')
    model.step(object_id+'.panels','Install the numbered roof and gable sheets; retain every supported seam and cut line shown in the packet.',parts=panels+gable_panels,
               connections=[skin_connection],prerequisites=[object_id+'.frame'],view=object_id+'.plan',exploded={pid:[0,0,200] for pid in panels})
    return dict(id=object_id,parts=parts,panels=panels,gable_panels=gable_panels,rafters=rafters,ridge=ridge,
                height=peak+panel,check_scope='geometry_and_fabrication')


def shed(model, *, object_id='shed', length=3048, depth=2438.4, wall_height=2438.4,
         door_width=914.4, window_width=650, slope=.5, wall_exceptions=None):
    """A detailed framing study whose site-dependent connections stay explicit."""
    floor=floor_frame(model,object_id=object_id+'.floor',length=length,depth=depth)
    z=floor['top'];d=89
    walls={}
    walls['front']=framed_wall(model,object_id=object_id+'.front',length=length,height=wall_height,
        location=cq.Location(cq.Vector(0,0,z)),openings=[dict(id='door',x=(length-door_width)/2,width=door_width,height=2032)],
        exceptions=(wall_exceptions or {}).get('front'))
    walls['back']=framed_wall(model,object_id=object_id+'.back',length=length,height=wall_height,
        location=cq.Location(cq.Vector(length,depth,z),cq.Vector(0,0,1),180),
        openings=[dict(id='window',x=(length-window_width)/2,width=window_width,sill=900,height=900)],
        exceptions=(wall_exceptions or {}).get('back'))
    for side,origin,angle in [('left',(0,depth-d,z),-90),('right',(length,d,z),90)]:
        walls[side]=framed_wall(model,object_id=object_id+'.'+side,length=depth-2*d,height=wall_height,
            location=cq.Location(cq.Vector(*origin),cq.Vector(0,0,1),angle),exceptions=(wall_exceptions or {}).get(side))
    roof=gable_roof(model,object_id=object_id+'.roof',length=length,depth=depth,wall_top=z+wall_height,slope=slope,
        bearing_parts={side:walls[side]['top'][-1] for side in ('front','back')},
        end_bearing_parts={side:walls[side]['top'][-1] for side in ('left','right')})
    for side,wall in walls.items():
        for plate in wall['bottom']:
            model.requirement(plate+'.deck_support','support',[plate,floor['panels'][0 if side=='left' else -1 if side=='right' else 0]],threshold=1,units='mm2')
    # Remove the one-panel shortcut for long front/back plates: supporting
    # contact is measured against the complete deck compound as an explicit
    # requirement set, without claiming that every sheet bears every plate.
    for side in ('front','back'):
        for plate in walls[side]['bottom']:
            model.requirements.pop(plate+'.deck_support',None)
            actual=[p for p in floor['panels'] if model.shapes[plate]['world'].distance(model.shapes[p]['world'])<.001]
            for panel_id in actual:model.requirement(plate+'.support.'+panel_id,'support',[plate,panel_id],threshold=1,units='mm2')
    all_wall_parts=[part for wall in walls.values() for part in wall['parts']]
    model.connection(object_id+'.wall_floor',parts=all_wall_parts+floor['parts']+floor['panels'],
        description='Raise and brace each wall, fasten adjoining corner studs together, and fix the bottom plates through the deck into the rim or blocking below.',
        unresolved=['Specify foundation bearing, ground anchorage, and wall hold-downs for the site.'])
    model.step(object_id+'.erect_walls','Raise, square and brace the four completed walls on the platform. Fasten the corners and confirm the door rough opening.',
        parts=all_wall_parts,connections=[object_id+'.wall_floor'],prerequisites=[floor['id']+'.deck']+[wall['id']+'.frame' for wall in walls.values()],
        view=walls['front']['id']+'.elevation')
    model.steps[roof['id']+'.frame']['prerequisites'].append(object_id+'.erect_walls')
    model.requirement(object_id+'.interference','collision_free',[pid for pid in model.objects if pid.startswith(object_id+'.')],threshold=0,units='mm3',
                      explanation='Native solid intersections between distinct framing and sheathing pieces.')
    model.notes += ['This packet details the frame and sheathing. Site foundation, load sizing, rated uplift/hold-down connections, roofing, flashing, cladding, door and window installation need project-specific details.',
                    'Member and fastener sizes in this study are fabrication inputs, not a structural analysis.']
    return dict(floor=floor,walls=walls,roof=roof)
