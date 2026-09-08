"""Rectangular wall framing, backed corners and coordinated enclosure edges."""
import math
from .assemblies import WallFrame, framed_opening, _number
from ._assembly import Builder, section, positions


def wall_frame(project, id, *, width, depth, height, stud_stock,
               frame=WallFrame(), spacing=16, openings=(), header_stock=None,
               spacer_stock=None, interior_finish=False, minimum_splice_offset=24,
               support_ids=(), assembly='Wall framing'):
    """Four walls, individual members and conventional lapped double top plates.

    Dimensions are outside framing. Openings use wall-local start/bottom/width/
    height; side-wall U starts after the front wall depth. Three-stud corners
    provide backing when interior_finish=True. Capacity and fastening are not
    inferred. The supplied splice offset defaults to the conventional IRC detail.
    """
    for value,name in ((width,'width'),(depth,'depth'),(height,'height'),
                       (minimum_splice_offset,'minimum_splice_offset')): _number(value,name)
    t,d=section(project,stud_stock)
    if min(width,depth)<=4*d or height<=3*t: raise ValueError('Wall envelope is too small')
    maximum=max(project.stocks[stud_stock].lengths)
    if maximum<=minimum_splice_offset+2*d:
        raise ValueError('Plate stock too short for the specified splice pattern')
    b=Builder(project,id,frame,'wall_frame',assembly)
    support_ids=list(dict.fromkeys(support_ids))
    if any(pid not in {p['id'] for p in project.parts} for pid in support_ids):
        raise ValueError('Unknown wall bearing support part')
    configs={
        'front': (WallFrame(frame.point(0,0,0),frame.angle,frame.inward),width),
        'back': (WallFrame(frame.point(0,depth,0),frame.angle,-frame.inward),width),
        'west': (WallFrame(frame.point(0,d,0),frame.angle+90*frame.inward,-frame.inward),depth-2*d),
        'east': (WallFrame(frame.point(width,d,0),frame.angle+90*frame.inward,frame.inward),depth-2*d),
    }
    bywall={name:[] for name in configs}
    names=set()
    for op in openings:
        op=dict(op)
        if op.get('wall') not in configs or not isinstance(op.get('id'),str) or not op['id'].strip() or op['id'] in names:
            raise ValueError('Openings need unique IDs and a front/back/west/east wall')
        names.add(op['id']);bywall[op['wall']].append(op)
    wall_parts={};opening_results={};cap_parts={};bottom_parts={}
    for name,(wf,length) in configs.items():
        wb=Builder(b.project,f'{id}.{name}',wf,'wall_frame',assembly)
        ops=sorted(bywall[name],key=lambda op:op['start'])
        for op in ops:
            for key in ('start','bottom'): _number(op[key],key,inclusive=True)
            for key in ('width','height'): _number(op[key],key)
            # Preserve corner framing/backing and the kings on either side.
            margin=d+t if name in ('front','back') and interior_finish else t
            if op['start']-2*t<margin or op['start']+op['width']+2*t>length-margin:
                raise ValueError('Opening conflicts with corner framing/backing')
        if any(a['start']+a['width']+4*t>c['start'] for a,c in zip(ops,ops[1:])):
            raise ValueError('Opening framing envelopes overlap')
        bottom_spans=[];cursor=0
        for op in ops:
            if op['bottom']==0:
                bottom_spans.append((cursor,op['start']));cursor=op['start']+op['width']
        bottom_spans.append((cursor,length))
        bottoms=[]
        for run,(a,e) in enumerate(bottom_spans):
            for j,(lo,hi) in enumerate(_segments(a,e,maximum,0)):
                bottoms.append(wb.box(f'bottom.{run}.{j}',stud_stock,(lo,0,0),(hi-lo,d,t)))
        bottom_parts[name]=bottoms
        for j,pid in enumerate(bottoms):
            if support_ids:
                part=next(p for p in wb.project.parts if p['id']==pid)
                wb.require(f'floor_bearing.{j}','Bottom plate bears on the floor assembly',
                    'minimum_total_contact',[pid,*support_ids],normal=[0,0,-1],
                    minimum_area=part['size'][0]*d)
        layers=[]
        for layer,z in enumerate((height-2*t,height-t)):
            a,e=(0,length) if layer==0 else ((d,length-d) if name in ('front','back') else (-d,length+d))
            caps=[]
            # Align the stagger to the lower run's datum, not the upper extent.
            offset=0 if layer==0 else minimum_splice_offset
            for j,(lo,hi) in enumerate(_segments(a,e,maximum,offset)):
                caps.append(wb.box(f'cap.{layer}.{j}',stud_stock,(lo,0,z),(hi-lo,d,t)))
            layers.append(caps)
        cap_parts[name]=layers
        along=wf.point(1,0,0);base=wf.point(0,0,0)
        wb.require('splices','Offset top-plate splices','plate_splice_offset',sum(layers,[]),
                   layers=layers,direction=[a-b for a,b in zip(along,base)],minimum_offset=minimum_splice_offset)
        us=positions(length,spacing,t)
        if name in ('front','back') and interior_finish:
            us=sorted(set(us+[d,length-d-t]))
        if any(y-x<t-.001 for x,y in zip(us,us[1:])):
            raise ValueError('Field stud layout conflicts with corner backing')
        field_ids=[]
        for i,u in enumerate(us):
            affected=next((op for op in ops if u<op['start']+op['width']+2*t and u+t>op['start']-2*t),None)
            if affected: continue
            pid=wb.box(f'stud.{i}',stud_stock,(u,0,t),(t,d,height-3*t))
            field_ids.append(pid)
            _foot_requirement(wb,pid,bottoms,t*d)
            wb.require(f'head.{i}','Stud meets lower top plate','minimum_total_contact',[pid,*layers[0]],minimum_area=t*d,normal=[0,0,1])
        for op in ops:
            fields=[(f'{id}.{name}.{op["id"]}.field.{i}',u) for i,u in enumerate(us)
                    if op['start']+t<=u and u+t<=op['start']+op['width']-t]
            opened=framed_opening(wb.project,f'{id}.{name}.{op["id"]}',frame=wf,
                start=op['start'],width=op['width'],bottom=op['bottom'],height=op['height'],wall_height=height,
                stud_stock=stud_stock,header_stock=header_stock,spacer_stock=spacer_stock,field_studs=fields,assembly=assembly)
            if op['bottom']>2*t:
                for edge,u in [('left',op['start']),('right',op['start']+op['width']-t)]:
                    pid=wb.box(f'{op["id"]}.sill_cripple.{edge}',stud_stock,(u,0,t),(t,d,op['bottom']-2*t))
                    _foot_requirement(wb,pid,bottoms,t*d)
                    wb.require(f'sill_bearing.{op["id"]}.{edge}','Window sill bears on edge cripple','minimum_contact',
                               [opened.roles['sill'],pid],minimum_area=t*d,normal=[0,0,-1])
            # Back both panel edges above the opening, where jack studs stop.
            _,header_depth=section(project,header_stock)
            z=op['bottom']+op['height']+header_depth
            if height-2*t>z:
                for edge,u in [('left',op['start']-t/2),('right',op['start']+op['width']-t/2)]:
                    pid=wb.box(f'{op["id"]}.edge_cripple.{edge}',stud_stock,(u,0,z),(t,d,height-2*t-z))
                    _foot_requirement(wb,pid,[v for r,v in opened.roles.items() if r.startswith('header.')],t*d)
            opened.include_in_clearance(wb.project.parts)
            opening_results[op['id']]=dict(opening=opened,wall=name,spec=op,frame=wf)
            for role,pid in opened.roles.items():
                wb.result.roles[f'{op["id"]}.{role}']=pid
                if role.startswith(('king.','jack.')) or role.endswith('.lower'):
                    _foot_requirement(wb,pid,bottoms,t*d)
        # Field studs already have full-height support requirements; opening
        # builders own their bearing/clearance and presence covers the rest.
        wall_parts[name]=wb.commit()
        b.result.roles.update({f'{name}.{role}':pid for role,pid in wall_parts[name].roles.items()})
    # Side-wall upper caps bridge the lower front/back plates at all four corners.
    for side in ('west','east'):
        for end,adjacent in enumerate(('front','back')):
            cap=cap_parts[side][1][0 if end==0 else -1]
            # Which end of the front/back lower run touches this side?
            lower=cap_parts[adjacent][0][0 if side=='west' else -1]
            b.require(f'lap.{side}.{adjacent}', 'Upper plate laps adjoining wall',
                      'minimum_contact',[cap,lower],minimum_area=d*d,normal=[0,0,-1])
    b.unverified('connections','Wall bracing, plate splice fastening, hold-downs, header capacity and load paths need the selected loads and connection design.')
    if not support_ids:
        b.unverified('floor_bearing','Wall-to-floor bearing is not specified; supply the floor support part IDs.')
    b.result.interfaces.update(width=width,depth=depth,height=height,wall_depth=d,
        stock_thickness=t,walls=wall_parts,openings=opening_results,caps=cap_parts,
        interior_finish=interior_finish,top_elevation=frame.origin[2]+height,
        bottoms=bottom_parts,support_ids=support_ids)
    return b.commit()


def _segments(start,end,maximum,offset):
    if end<=start: return []
    cuts=[start]
    n=1
    while n*maximum-offset<end-.001:
        v=n*maximum-offset
        if v>start+.001: cuts.append(v)
        n+=1
    cuts.append(end)
    if any(b-a>maximum+.001 for a,b in zip(cuts,cuts[1:])):
        raise ValueError('Plate splice pattern exceeds available stock')
    return list(zip(cuts,cuts[1:]))


def _foot_requirement(builder,pid,bottoms,area):
    # Choose the actual containing plate segment, not all segments.
    import solid_geometry as geo
    part=next(p for p in builder.project.parts if p['id']==pid)
    for bottom in bottoms:
        support=next(p for p in builder.project.parts if p['id']==bottom)
        contact,_=geo.contact_area(geo.solids(part),geo.solids(support),direction=(0,0,-1))
        if contact>=area-1e-6:
            builder.require(f'foot.{pid}','Vertical member bears on bottom plate','minimum_contact',
                            [pid,bottom],minimum_area=area,normal=[0,0,-1])
            return
    # Do not silently accept a stud straddling a splice. Both pieces may provide
    # support; use measured bearing strips through panel_support in that case.
    builder.require(f'foot.{pid}','Vertical member bears on bottom plates','panel_support',
                    [pid,*bottoms],thickness_axis=2,bearing_width=min(part['size'][:2])/2)


def wall_enclosure(project, id, *, walls, sheathing_stock, siding_stock,
                   trim_stock, sheathing_thickness=.5, siding_thickness=.625,
                   trim_gap=.125, liner_stock=None, liner_thickness=.5, exterior_height=None,
                   roof=None, exterior_bottom=0, opening_trim_stock=None,
                   opening_trim_width=4, opening_trim_overlap=.5, door_kickboard_stock=None,
                   siding_layout='centered', siding_offset=0, assembly='Wall enclosure'):
    """Board-trim corners and tiled skins sharing the wall/opening datums.

    Thicknesses and gap are product inputs. This builder closes a rectangular
    shell with two butt-jointed vertical trim boards at each corner. It does not
    certify WRB, flashing, sealant, fastening or a moisture strategy.
    """
    for v,n in ((sheathing_thickness,'sheathing_thickness'),(siding_thickness,'siding_thickness'),(liner_thickness,'liner_thickness')):
        _number(v,n)
    _number(trim_gap,'trim_gap',inclusive=True)
    if siding_layout not in ('centered','start'):
        raise ValueError('Siding layout must be centered or start')
    _number(siding_offset,'siding_offset',inclusive=True)
    if siding_layout=='centered' and siding_offset:
        raise ValueError('Siding offset applies only to the start layout')
    tt,tw=section(project,trim_stock)
    if opening_trim_stock:
        ot,ow=section(project,opening_trim_stock)
        _number(opening_trim_width,'opening trim width')
        _number(opening_trim_overlap,'opening trim overlap',inclusive=True)
        if ow<opening_trim_width or opening_trim_width<=opening_trim_overlap or ot<siding_thickness:
            raise ValueError('Opening trim blank must fit the finished width, cover siding and retain sheathing bearing')
    for stock in (sheathing_stock,siding_stock,liner_stock):
        if stock and (stock not in project.stocks or not project.stocks[stock].sheet):
            raise ValueError('Skins require registered sheet stock')
    if siding_offset>=min(project.stocks[siding_stock].sheet):
        raise ValueError('Siding offset must be smaller than one sheet width')
    q=walls.interfaces;w,d,h,wd=q['width'],q['depth'],q['height'],q['wall_depth']
    if isinstance(exterior_bottom,bool) or not isinstance(exterior_bottom,(int,float)) or not math.isfinite(exterior_bottom) or exterior_bottom>0:
        raise ValueError('Exterior bottom must be a finite offset at or below the wall base')
    if door_kickboard_stock:
        kt,kh=section(project,door_kickboard_stock)
        if not opening_trim_stock or exterior_bottom>=0 or kh < -exterior_bottom or abs(kt-ot)>.001:
            raise ValueError('Door kickboard needs matching casing thickness and a blank spanning the exposed floor rim')
    eh=(roof.interfaces['soffit_bottom']-walls.frame.origin[2] if roof else h) if exterior_height is None else exterior_height
    _number(eh,'exterior_height')
    if roof and abs(eh-(roof.interfaces['soffit_bottom']-walls.frame.origin[2]))>.001:
        raise ValueError('Exterior height must match the supplied roof soffit datum')
    if eh>h: raise ValueError('Exterior skin height exceeds wall framing; model gable infill separately')
    if any(info['spec']['bottom']+info['spec']['height']>eh for info in q['openings'].values()):
        raise ValueError('Exterior skin height must cover all wall openings')
    if liner_stock and not q['interior_finish']:
        raise ValueError('Finished interior requires a wall-frame backing plan')
    if tt<siding_thickness or tw<=sheathing_thickness+tt+trim_gap:
        raise ValueError('Corner trim must cover siding thickness and leave a usable corner width')
    b=Builder(project,id,walls.frame,'wall_enclosure',assembly)
    roof_data=None
    if roof:
        rq=roof.interfaces;p=sheathing_thickness+tt;side_run=tw-p
        if abs(rq['span']-w)>.001 or abs(rq['length']-d)>.001:
            raise ValueError('Enclosure roof must span the front/back walls and run between them')
        angle=math.radians(roof.frame.angle);cs,sn=math.cos(angle),math.sin(angle)
        corners=[]
        for x,y in ((0,0),(w,0),(0,d),(w,d)):
            point=walls.frame.point(x,y,h);delta=[a-z for a,z in zip(point,roof.frame.origin)]
            u=delta[0]*cs+delta[1]*sn;v=(-delta[0]*sn+delta[1]*cs)*roof.frame.inward
            corners.append((u,v))
            if min(abs(u),abs(u-d))>.001 or min(abs(v),abs(v-w))>.001 or abs(delta[2])>.001:
                raise ValueError('Enclosure roof and walls must share their plan and plate datum')
        if abs(corners[0][0]-corners[1][0])>.001 or abs(corners[2][0]-corners[3][0])>.001 or abs(corners[0][0]-corners[2][0])<.001:
            raise ValueError('Roof gables must align with the front/back enclosure walls')
        clearance=rq.get('corner_trim_clearance')
        if not clearance or abs(clearance['projection']-p)>.001 or abs(clearance['side_run']-side_run)>.001:
            raise ValueError('Roof soffit trim clearances must match the enclosure trim dimensions')
        if side_run<=0:raise ValueError('Trim must extend inward past the corner')
        slope=rq['pitch']/12;c=1/math.sqrt(1+slope*slope)
        base=rq['soffit_top']-walls.frame.origin[2]
        corner=h-slope*rq['plate_depth']-rq['soffit_thickness']/c
        ridge_bottom=rq['ridge_top']-rq['ridge_depth']-walls.frame.origin[2]
        ridge_left=(w-rq['ridge_thickness'])/2;ridge_right=w-ridge_left
        eave=next(part for part in project.parts if part['id']==roof.roles['fascia.eave.0'])
        ft,_=section(project,eave['stock'])
        if not sheathing_thickness<ft<p:
            raise ValueError('Scribed corner trim requires the bird-box back to overlap only its inner depth')
        if base+rq['soffit_nailer_depth']>=corner-p*slope:
            raise ValueError('Roof ledger leaves no room for the upper corner trim')
        roof_data=dict(base=base,ledger_top=base+rq['soffit_nailer_depth'],corner=corner,
                       slope=slope,projection=p,side_run=side_run,closure_thickness=ft)
        top=[(0,corner),(ridge_left,corner+ridge_left*slope),
             (ridge_left,ridge_bottom),(ridge_right,ridge_bottom),
             (ridge_right,corner+ridge_left*slope),(w,corner)]
        if rq.get('ridge_termination')=='wall':top=[(0,corner),(w/2,corner+w/2*slope),(w,corner)]
        roof_data['gable']=[(0,eh),(w,eh),*reversed(top)]
    wallmap=q['walls'];all_frame=walls.part_ids
    trim_ids={}
    for name,wall in wallmap.items():
        wf=wall.frame
        side=name in ('west','east')
        length=d if side else w
        ext=WallFrame(wf.point(-wd if side else 0,0,0),wf.angle,wf.inward)
        wb=Builder(b.project,f'{id}.{name}',ext,'wall_enclosure',assembly)
        start=-sheathing_thickness-(tt if side else 0)
        end=length+sheathing_thickness+(tt if side else 0)
        if roof_data:
            left=_scribed_corner_trim(wb,'trim.start',trim_stock,start,length,False,side,tt,tw,exterior_bottom,roof_data)
            right=_scribed_corner_trim(wb,'trim.end',trim_stock,start,length,True,side,tt,tw,exterior_bottom,roof_data)
        else:
            left=wb.box('trim.start',trim_stock,(start,-sheathing_thickness-tt,exterior_bottom),(tw,tt,eh-exterior_bottom))
            right=wb.box('trim.end',trim_stock,(end-tw,-sheathing_thickness-tt,exterior_bottom),(tw,tt,eh-exterior_bottom))
        trim_ids[name]=(left,right)
        ops=[];trim_ops=[];siding_ops=[]
        for info in q['openings'].values():
            if info['wall']==name:
                op=info['spec'];a=op['start']+(wd if side else 0)
                ops.append((a,op['width'],op['bottom'],op['height']))
                if opening_trim_stock:
                    overlap=opening_trim_overlap;face=opening_trim_width
                    if min(op['width'],op['height'])<=2*overlap:raise ValueError('Opening trim consumes the opening')
                    lo=op['bottom'] if op['bottom']==0 else op['bottom']+overlap-face
                    hi=op['bottom']+op['height']-overlap+face
                    ua=a+overlap-face;ue=a+op['width']-overlap+face
                    if ua-trim_gap<start+tw+trim_gap or ue+trim_gap>end-tw-trim_gap or lo<exterior_bottom:
                        raise ValueError('Opening trim must fit between corners, floor and roof enclosure')
                    if hi+trim_gap>eh:
                        if not roof_data or side or abs(_outline_area(_clip_upright(roof_data['gable'],ua-trim_gap,ue+trim_gap,eh,hi+trim_gap))-(ue-ua+2*trim_gap)*(hi+trim_gap-eh))>.001:
                            raise ValueError('Opening trim must fit below the gable roof')
                    cut_bottom=(exterior_bottom if door_kickboard_stock else lo) if op['bottom']==0 else lo-trim_gap
                    cut=(ua-trim_gap,ue-ua+2*trim_gap,cut_bottom,hi-cut_bottom+trim_gap)
                    if any(cut[0]<v[0]+v[1] and cut[0]+cut[1]>v[0] and cut[2]<v[2]+v[3] and cut[2]+cut[3]>v[2] for v in siding_ops):
                        raise ValueError('Opening trim surrounds overlap')
                    siding_ops.append(cut);trim_ops.append((op['id'],a,op['width'],op['bottom'],op['height']))
                else:siding_ops.append(ops[-1])
        sheath_ids=[]
        def skin(prefix,stock,u0,u1,v,thickness,openings,lining=False):
            sheet=project.stocks[stock].sheet
            max_u,min_z=sorted(sheet)
            if prefix=='siding':
                made=[];cuts=[u0,*_siding_sheet_cuts(u0,u1,max_u,siding_layout,siding_offset),u1]
                for i,(a,e) in enumerate(zip(cuts,cuts[1:])):
                    z=exterior_bottom;j=0
                    while z<eh-.001:
                        top=min(eh,z+min_z)
                        for k,polys in enumerate(_sheet_cut_regions(a,e,z,top,openings)):
                            role=f'{prefix}.{i}.{j}.{k}'
                            points=[point for poly in polys for point in poly]
                            pid=_upright_outline(wb,role,stock,points,v,thickness,
                                layers=[dict(x=[0,thickness],outlines=polys)])
                            made.append(pid)
                            zero=ext.point(0,0,0);inside=ext.point(0,1,0)
                            wb.require(f'siding_backing.{i}.{j}.{k}','Cut siding sheet meets sheathing over its full footprint',
                                'minimum_total_contact',[pid,*sheath_ids],minimum_area=sum(_outline_area(poly) for poly in polys),
                                normal=[x-y for x,y in zip(inside,zero)])
                            along=ext.point(1,0,0);direction=[x-y for x,y in zip(along,zero)]
                            if abs(min(x for x,z in points)-u0)<.001:
                                wb.require(f'corner.start.{i}.{j}.{k}','Siding meets start trim with specified joint','surface_gap',
                                    [left,pid],direction=direction,gap=trim_gap)
                            if abs(max(x for x,z in points)-u1)<.001:
                                wb.require(f'corner.end.{i}.{j}.{k}','Siding meets end trim with specified joint','surface_gap',
                                    [pid,right],direction=direction,gap=trim_gap)
                        z=top;j+=1
                return made
            cuts={u0,u1}
            # Structural sheathing and lining retain their framing datum.
            offset=wd if side else 0
            pos=offset
            while pos<u1:
                if u0<pos<u1: cuts.add(pos)
                pos+=max_u
            for a,width,bottom,height in openings:
                if u0<a<u1: cuts.add(a)
                if u0<a+width<u1: cuts.add(a+width)
            cuts=sorted(cuts)
            made=[]
            for i,(a,e) in enumerate(zip(cuts,cuts[1:])):
                top_height=h if lining else eh
                bottom_height=0 if lining else exterior_bottom
                vertical=[(bottom_height,top_height)]
                hit=next((op for op in openings if a>=op[0]-.001 and e<=op[0]+op[1]+.001),None)
                if hit: vertical=[(bottom_height,hit[2]),(hit[2]+hit[3],top_height)]
                for j,(lo,hi) in enumerate(vertical):
                    z=lo;k=0
                    while z<hi-.001:
                        top=min(hi,z+min_z)
                        pid=wb.box(f'{prefix}.{i}.{j}.{k}',stock,(a,v,z),(e-a,thickness,top-z))
                        made.append(pid)
                        if lining:
                            wb.require(f'backing.{prefix}.{i}.{j}.{k}','Interior finish edge backing','panel_support',
                                [pid,*all_frame],thickness_axis=1,support_face='min' if ext.inward==1 else 'max',bearing_width=.5)
                        if prefix=='sheathing': sheath_ids.append(pid)
                        z=top;k+=1
            return made
        skin('sheathing',sheathing_stock,0 if side else -sheathing_thickness,
             length if side else length+sheathing_thickness,-sheathing_thickness,sheathing_thickness,ops)
        skin('siding',siding_stock,start+tw+trim_gap,end-tw-trim_gap,
             -sheathing_thickness-siding_thickness,siding_thickness,siding_ops)
        if liner_stock:
            a=wd+liner_thickness if side else wd
            e=length-wd-liner_thickness if side else length-wd
            skin('liner',liner_stock,a,e,wd,liner_thickness,ops,True)
        if roof_data:
            if not side:
                upper_sheathing=[]
                for prefix,stock,u0,u1,v,thickness in (
                    ('upper.sheathing',sheathing_stock,0,length,-sheathing_thickness,sheathing_thickness),
                    ('upper.siding',siding_stock,start+tw+trim_gap,end-tw-trim_gap,-sheathing_thickness-siding_thickness,siding_thickness)):
                    sheet_w,sheet_h=sorted(project.stocks[stock].sheet)
                    if prefix=='upper.siding':
                        cuts=[u0,*_siding_sheet_cuts(u0,u1,sheet_w,siding_layout,siding_offset),u1]
                        for i,(a,e) in enumerate(zip(cuts,cuts[1:])):
                            z=eh;j=0;roof_top=max(v[1] for v in roof_data['gable'])
                            while z<roof_top-.001:
                                top_z=min(roof_top,z+sheet_h)
                                for k,polys in enumerate(_sheet_cut_regions(a,e,z,top_z,siding_ops if opening_trim_stock else [])):
                                    clipped=[]
                                    for poly in polys:
                                        xs=[x for x,z in poly];zs=[z for x,z in poly]
                                        cut=_clip_upright(roof_data['gable'],min(xs),max(xs),min(zs),max(zs))
                                        if cut:clipped.append(cut)
                                    if not clipped:continue
                                    for piece,component in enumerate(_connected_sheet_regions(clipped)):
                                        role=f'{prefix}.{i}.{j}'+(f'.{k}.{piece}' if k or piece else '')
                                        points=[point for poly in component for point in poly]
                                        pid=_upright_outline(wb,role,stock,points,v,thickness,
                                            layers=[dict(x=[0,thickness],outlines=component)])
                                        normal=[x-y for x,y in zip(ext.point(0,1,0),ext.point(0,0,0))]
                                        wb.require(f'{role}.backing','Cut gable siding sheet covers its full sheathing footprint',
                                            'minimum_total_contact',[pid,*upper_sheathing],
                                            minimum_area=sum(_outline_area(poly) for poly in component),normal=normal)
                                z=top_z;j+=1
                        continue
                    cutouts=siding_ops if opening_trim_stock and prefix=='upper.siding' else []
                    sheet_cuts=(_siding_sheet_cuts(u0,u1,sheet_w,siding_layout,siding_offset) if prefix=='upper.siding' else
                                [length/2,*[x for x in _multiples_between(sheet_w,length) if u0<x<u1]])
                    cuts=sorted({u0,u1,*sheet_cuts,
                                 *[x for op in cutouts for x in (op[0],op[0]+op[1]) if u0<x<u1]})
                    for i,(a,e) in enumerate(zip(cuts,cuts[1:])):
                        z=eh;j=0
                        roof_top=max(v[1] for v in roof_data['gable'])
                        vertical_cuts=sorted({eh,roof_top,*[v for op in cutouts for v in (op[2],op[2]+op[3]) if eh<v<roof_top]})
                        while z<roof_top-.001:
                            top_z=min(z+sheet_h,next(v for v in vertical_cuts if v>z+.001))
                            blocked=any(a>=op[0]-.001 and e<=op[0]+op[1]+.001 and z>=op[2]-.001 and top_z<=op[2]+op[3]+.001 for op in cutouts)
                            points=[] if blocked else _clip_upright(roof_data['gable'],a,e,z,top_z)
                            if points:
                                role=f'{prefix}.{i}.{j}'
                                pid=_upright_outline(wb,role,stock,points,v,thickness)
                                if prefix=='upper.sheathing':
                                    upper_sheathing.append(pid);sheath_ids.append(pid)
                                else:
                                    normal=[x-y for x,y in zip(ext.point(0,1,0),ext.point(0,0,0))]
                                    wb.require(f'{role}.backing','Gable siding covers its full sheathing footprint','minimum_total_contact',
                                        [pid,*upper_sheathing],minimum_area=_outline_area(points),normal=normal)
                            z=top_z;j+=1
                normal=[x-y for x,y in zip(ext.point(0,1,0),ext.point(0,0,0))]
                trim_in=tw-sheathing_thickness
                area=trim_in*(roof_data['corner']+roof_data['slope']*trim_in/2-eh)
                for label,pid in (('start',left),('end',right)):
                    wb.require(f'trim_upper.{label}','Corner trim extends to the gable soffit over sheathing','minimum_total_contact',
                        [pid,*upper_sheathing],minimum_area=area,normal=normal)
            else:
                upper=roof_data['corner']-roof_data['projection']*roof_data['slope']
                lower=roof_data['ledger_top'];run=roof_data['side_run']
                normal=[x-y for x,y in zip(ext.point(0,1,0),ext.point(0,0,0))]
                for label,u,pid in (('start',0,left),('end',length-run,right)):
                    backing=wb.box(f'trim_backing.upper.{label}',sheathing_stock,
                        (u,-sheathing_thickness,lower),(run,sheathing_thickness,upper-lower))
                    wb.require(f'trim_upper.{label}','Upper corner trim bears on its sheathing backing','minimum_contact',
                        [pid,backing],minimum_area=run*(upper-lower),normal=normal)
                    wb.require(f'trim_backing.upper.{label}.host','Upper trim backing meets wall framing','minimum_total_contact',
                        [backing,*all_frame],minimum_area=run*(upper-lower),normal=normal)
        if opening_trim_stock:
            for opid,a,width,bottom,height in trim_ops:
                _opening_casing(wb,opid,opening_trim_stock,a,width,bottom,height,
                                sheathing_thickness,opening_trim_width,opening_trim_overlap,sheath_ids)
                if door_kickboard_stock and bottom==0:
                    face=opening_trim_width;overlap=opening_trim_overlap
                    kw=width-2*overlap+2*face;ka=a+overlap-face
                    pid=wb.box(f'opening_trim.{opid}.kickboard',door_kickboard_stock,
                               (ka,-sheathing_thickness-kt,exterior_bottom),(kw,kt,kh))
                    part=wb.project.parts[-1];size=[kw,kt,-exterior_bottom]
                    center=ext.point(ka+kw/2,-sheathing_thickness-kt/2,exterior_bottom/2)
                    part.update(blank_size=[kw,kt,kh],size=size,origin=[v-d/2 for v,d in zip(center,size)],
                                note='Trim kickboard under door, ripped to cover the exposed floor rim; full casing width.')
                    normal=[v-z for v,z in zip(ext.point(0,1,0),ext.point(0,0,0))]
                    wb.require(f'opening_trim.{opid}.kickboard.backing','Door kickboard bears on sheathing',
                               'minimum_total_contact',[pid,*sheath_ids],minimum_area=kw*(-exterior_bottom),normal=normal)
                    for edge in ('left','right'):
                        wb.require(f'opening_trim.{opid}.kickboard.{edge}.joint','Door casing meets kickboard',
                                   'minimum_contact',[pid,wb.result.roles[f'opening_trim.{opid}.{edge}']],minimum_area=face*kt)
        # All finishes participate in host opening clearance; intended units do not.
        for info in q['openings'].values():
            if info['wall']==name: info['opening'].include_in_clearance(wb.project.parts)
        result=wb.commit()
        b.result.roles.update({f'{name}.{role}':pid for role,pid in result.roles.items()})
    for side in ('west','east'):
        for end,face in enumerate(('front','back')):
            b.require(f'trim_joint.{side}.{face}','Corner trim boards meet','minimum_contact',
                [trim_ids[side][end],trim_ids[face][0 if side=='west' else 1]],minimum_area=tt*(eh-exterior_bottom))
    if eh<h and not roof:
        b.unverified('upper_enclosure','Exterior skins stop at the selected soffit/infill datum. Upper wall and gable weather closure must be completed with the roof enclosure.')
    b.unverified('weather_detail','WRB, corner backing/fastening, window/door flashing, sealant joints and moisture control require the selected enclosure product details.')
    b.unverified('sheathing_support','Exterior sheathing fastening and intermediate panel-edge blocking are not fully verified by this enclosure builder.')
    b.result.interfaces.update(exterior_height=eh,exterior_bottom=exterior_bottom,roof_id=roof.id if roof else None,
                              opening_trim_width=opening_trim_width if opening_trim_stock else None,
                              opening_trim_overlap=opening_trim_overlap if opening_trim_stock else None,
                              trim_gap=trim_gap,wall_depth=wd,sheathing_thickness=sheathing_thickness,
                              siding_thickness=siding_thickness,liner_thickness=liner_thickness if liner_stock else 0)
    result=b.commit()
    if roof:
        project.validation['unverified'][:]=[item for item in project.validation['unverified'] if item.get('rule')!=f'{roof.id}.gable_cladding']
    return result


def _outline_area(points):
    return abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(points,points[1:]+points[:1])))/2


def _clip_upright(points,u0,u1,z0,z1):
    import solid_geometry as geo
    raw=geo.intersect2d(points,[(u0,z0),(u1,z0),(u1,z1),(u0,z1)])
    clean=[]
    for p in raw:
        if not clean or math.dist(p,clean[-1])>1e-7:clean.append(p)
    if len(clean)>1 and math.dist(clean[0],clean[-1])<1e-7:clean.pop()
    if len(clean)<3 or _outline_area(clean)<1e-7:return []
    return clean


def _sheet_cut_regions(a,e,z,top,openings):
    """Connected regions of one sheet after rectangular opening cuts."""
    rectangles=[(a,e,z,top)]
    for u,width,lo,height in openings:
        remaining=[]
        for x0,x1,z0,z1 in rectangles:
            l=max(x0,u);r=min(x1,u+width);b=max(z0,lo);t=min(z1,lo+height)
            if r-l<1e-8 or t-b<1e-8:
                remaining.append((x0,x1,z0,z1));continue
            for rect in ((x0,l,z0,z1),(r,x1,z0,z1),(l,r,z0,b),(l,r,t,z1)):
                if rect[1]-rect[0]>1e-8 and rect[3]-rect[2]>1e-8:remaining.append(rect)
        rectangles=remaining
    return _connected_sheet_regions([[(a,z),(e,z),(e,t),(a,t)] for a,e,z,t in rectangles])


def _connected_sheet_regions(polys):
    def adjacent(a,b):
        for p,q in zip(a,a[1:]+a[:1]):
            dx=q[0]-p[0];dz=q[1]-p[1];length=math.hypot(dx,dz)
            if length<1e-8:continue
            for r,t in zip(b,b[1:]+b[:1]):
                if any(abs(dx*(v[1]-p[1])-dz*(v[0]-p[0]))>1e-7*length for v in (r,t)):continue
                positions=[((v[0]-p[0])*dx+(v[1]-p[1])*dz)/length for v in (r,t)]
                if min(length,max(positions))-max(0,min(positions))>1e-8:return True
        return False
    pending=list(polys);groups=[]
    while pending:
        group=[pending.pop()];changed=True
        while changed:
            changed=False
            for poly in pending[:]:
                if any(adjacent(poly,member) for member in group):
                    group.append(poly);pending.remove(poly);changed=True
        groups.append(group)
    return groups


def _siding_sheet_cuts(start,end,sheet_width,layout,offset):
    if layout=='centered':return _centered_sheet_cuts(start,end,sheet_width)
    # Offset is the first cut's distance from the finished wall edge; zero is a full sheet.
    cuts=[];position=start+(offset or sheet_width)
    while position<end-1e-8:
        cuts.append(position);position+=sheet_width
    return cuts


def _centered_sheet_cuts(start,end,sheet_width):
    """Full interior sheets with equal end panels, each at least half a sheet."""
    count=max(1,math.ceil((end-start)/sheet_width-1e-10))
    if count==1:return []
    edge=((end-start)-(count-2)*sheet_width)/2
    return [start+edge+i*sheet_width for i in range(count-1)]


def _multiples_between(step,length):
    i=1
    while i*step<length:
        yield i*step;i+=1


def _upright_outline(b,role,stock,points,v,thickness,layers=None,blank_width=None):
    """Vertical U/Z cut, extruded in the wall's inward V direction."""
    u0=min(u for u,z in points);u1=max(u for u,z in points)
    z0=min(z for u,z in points);z1=max(z for u,z in points)
    width=blank_width or u1-u0;size=(thickness,width,z1-z0)
    center=b.result.frame.point(u0+width/2,v+thickness/2,(z0+z1)/2)
    def outline(poly):return [(u0+width-u if b.result.frame.inward==1 else u-u0,z-z0) for u,z in poly]
    pid=f'{b.result.id}.{role}';rotation=(0,0,b.result.frame.angle+90*b.result.frame.inward)
    origin=tuple(c-d/2 for c,d in zip(center,size))
    if layers:
        transformed=[dict(x=layer['x'],outlines=[outline(poly) for poly in layer['outlines']]) for layer in layers]
        b.project.layered_prism(pid,b.assembly,stock,size,origin,transformed,rotation=rotation,
            note=('One corner-trim blank, scribed around the bird-box back and soffit ledger.' if role.startswith('trim.')
                  else 'One siding sheet with connected opening and roof cuts.'))
    else:b.project.polygon_prism(pid,b.assembly,stock,size,origin,outline(points),rotation=rotation)
    return b.register(role,b.project.parts[-1])


def _scribed_corner_trim(b,role,stock,start,length,reverse,side,tt,tw,bottom,q):
    lo=start;hi=start+tw;base=q['base'];ledger=q['ledger_top']
    if side:
        top=q['corner']-q['projection']*q['slope']
        outer=[(lo,bottom),(hi,bottom),(hi,base),(0,base),(0,ledger),(hi,ledger),(hi,top),(lo,top)]
        lower=[(lo,bottom),(hi,bottom),(hi,base),(lo,base)]
        upper=[(0,ledger),(hi,ledger),(hi,top),(0,top)]
        split=q['projection']-q['closure_thickness']
        layers=[dict(x=[0,split],outlines=[outer]),dict(x=[split,tt],outlines=[lower,upper])]
        points=[(lo,bottom),(hi,bottom),(hi,top),(lo,top)]
    else:
        top=q['corner']+hi*q['slope']
        points=[(lo,bottom),(hi,bottom),(hi,top),(0,q['corner']),(0,base),(lo,base)]
        layers=None
    if reverse:
        points=[(length-u,z) for u,z in points]
        if layers:
            for layer in layers:layer['outlines']=[[(length-u,z) for u,z in poly] for poly in layer['outlines']]
    return _upright_outline(b,role,stock,points,-q['projection'],tt,layers,tw)


def plate_junction(project, id, *, main_length, branch_length, branch_at,
                   stock, frame=WallFrame(), assembly='Plate junction'):
    """Local L/T junction: bottom of first top plate at frame Z.

    Main wall runs U; branch begins at its inner V face. The second branch cap
    laps across the main wall. Host walls omit displaced plates before calling.
    """
    t,d=section(project,stock)
    for v,n in ((main_length,'main_length'),(branch_length,'branch_length')): _number(v,n)
    _number(branch_at,'branch_at',inclusive=True)
    if branch_at+d>main_length: raise ValueError('Branch lies beyond main wall')
    b=Builder(project,id,frame,'plate_junction',assembly)
    main=b.box('lower.main',stock,(0,0,0),(main_length,d,t))
    branch=b.box('lower.branch',stock,(branch_at,d,0),(d,branch_length,t))
    cap=b.box('upper.branch',stock,(branch_at,0,t),(d,branch_length+d,t))
    for name,a,e in [('left',0,branch_at),('right',branch_at+d,main_length)]:
        if e>a:
            pid=b.box(f'upper.{name}',stock,(a,0,t),(e-a,d,t))
            b.require(f'support.{name}','Upper main cap bearing','minimum_contact',[pid,main],minimum_area=(e-a)*d,normal=[0,0,-1])
    b.require('lap','Branch cap laps main wall','minimum_contact',[cap,main],minimum_area=d*d,normal=[0,0,-1])
    b.require('branch_bearing','Branch cap bears on branch','minimum_contact',[cap,branch],minimum_area=d*branch_length,normal=[0,0,-1])
    b.unverified('fasteners','Plate junction fastening and connection capacity remain to specify.')
    return b.commit()


def _opening_casing(b,id,stock,u,width,bottom,height,sheathing,face,overlap,supports):
    """Butt-jointed casing, ripped from one purchasable blank per board.

    Inner edges meet a unit with the matching installation gap. The door has
    jambs/head only; a raised opening also receives a sill/apron board.
    """
    thickness,blank_face=section(b.project,stock)
    left=u+overlap;right=u+width-overlap
    low=bottom+overlap if bottom else 0;high=bottom+height-overlap
    rectangles=[('left',left-face,low,face,high-low,0),
                ('right',right,low,face,high-low,0),
                ('head',left-face,high,right-left+2*face,face,2)]
    if bottom:rectangles.append(('sill',left-face,low-face,right-left+2*face,face,2))
    zero=b.result.frame.point(0,0,0);inside=b.result.frame.point(0,1,0)
    inward=[a-z for a,z in zip(inside,zero)];ids={}
    for name,a,z,w,h,axis in rectangles:
        role=f'opening_trim.{id}.{name}'
        size=[w,thickness,h];blank=list(size);blank[axis]=blank_face
        pid=b.box(role,stock,(a,-sheathing-thickness,z),blank)
        part=b.project.parts[-1]
        center=b.result.frame.point(a+w/2,-sheathing-thickness/2,z+h/2)
        part.update(size=size,origin=[v-d/2 for v,d in zip(center,size)],blank_size=blank,
                    note=f'Exterior casing: {face:g} in finished face ripped from {blank_face:g} in stock. Concealed installation gap overlap {overlap:g} in.')
        missing=max(0,min(a+w,u+width)-max(a,u))*max(0,min(z+h,bottom+height)-max(z,bottom))
        b.require(role+'.backing','Opening trim bears on sheathing','minimum_total_contact',
                  [pid,*supports],normal=inward,minimum_area=w*h-missing)
        direction=b.result.frame.point(1,0,0) if axis==0 else b.result.frame.point(0,0,1)
        b.require(role+'.width','Exterior trim retains specified finished face','minimum_section',
                  [pid],thickness_axis=1,depth_axis=axis,minimum_thickness=thickness,
                  minimum_depth=face,depth_direction=[v-o for v,o in zip(direction,zero)])
        ids[name]=pid
    for end in ('head','sill'):
        if end in ids:
            for side in ('left','right'):
                b.require(f'opening_trim.{id}.{end}.{side}.joint','Opening trim butt joint','minimum_contact',
                          [ids[end],ids[side]],minimum_area=face*thickness)
