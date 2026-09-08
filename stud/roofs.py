"""Sawn-rafter gable roofs with actual birdsmouths and configurable edges."""
import math
from .assemblies import WallFrame, _number
from ._assembly import Builder, section, positions
from .span_tables import select_rafter_size


def _tilted_rotation(yaw, pitch):
    """XYZ Euler representation of a horizontal yaw after a local X pitch."""
    y,p=map(math.radians,(yaw,pitch))
    return tuple(map(math.degrees,(math.atan2(math.cos(y)*math.sin(p),math.cos(p)),
                                  math.asin(math.sin(y)*math.sin(p)),
                                  math.atan2(math.sin(y)*math.cos(p),math.cos(y)))))


def sawn_rafter(project, id, *, run, plate_depth, pitch, overhang, stock,
                maximum_notch, minimum_remaining, notch_basis,
                frame=WallFrame(), plate_ids=(), assembly='Roof rafters'):
    """U is rafter thickness; V runs uphill from the exterior plate face.

    frame Z is the plate top. run reaches the ridge face; pitch is rise per 12.
    The plumb-cut, birdsmouth-notched member retains one rectangular stock blank.
    Limits are supplied by the design, not a built-in structural approval.
    """
    t,h=section(project,stock)
    for v,n in ((run,'run'),(plate_depth,'plate_depth'),(pitch,'pitch'),
                (minimum_remaining,'minimum_remaining')): _number(v,n)
    for v,n in ((overhang,'overhang'),(maximum_notch,'maximum_notch')): _number(v,n,inclusive=True)
    if run<=plate_depth or not str(notch_basis).strip(): raise ValueError('Rafter needs a clear run and sourced notch limits')
    theta=math.atan(pitch/12);c,s=math.cos(theta),math.sin(theta);slope=pitch/12
    cut=plate_depth*slope*c
    if cut>maximum_notch+.001 or h-cut<minimum_remaining-.001:
        raise ValueError('Birdsmouth exceeds supplied notch/remaining-section limits')
    b=Builder(project,id,frame,'sawn_rafter',assembly)
    y0=-overhang;z0=slope*(y0-plate_depth)
    bottom=lambda y:slope*(y-plate_depth)
    # World-like coordinates in the wall-local V/Z section; then unpitch them.
    points=[]
    if overhang>0: points.extend([(y0,bottom(y0)),(0,bottom(0))])
    points.extend([(0,0),(plate_depth,0),(run,bottom(run)),
                   (run,bottom(run)+h/c),(y0,bottom(y0)+h/c)])
    outline=[((y-y0)*c+(z-z0)*s, -(y-y0)*s+(z-z0)*c) for y,z in points]
    outline=[(max(0,y),max(0,z)) for y,z in outline]
    length=max(y for y,z in outline)
    local_center_y=y0+length/2*c-h/2*s
    local_center_z=z0+length/2*s+h/2*c
    center=frame.point(t/2,local_center_y,local_center_z)
    yaw=frame.angle+(180 if frame.inward==-1 else 0)
    rotation=_tilted_rotation(yaw,math.degrees(theta))
    pid=f'{id}.member'
    b.project.polygon_prism(pid,assembly,stock,(t,length,h),
        (center[0]-t/2,center[1]-length/2,center[2]-h/2),outline,rotation=rotation,
        note='One sawn stock blank; actual plumb end cuts and birdsmouth seat. '+notch_basis)
    b.register('member',b.project.parts[-1])
    seat=[(0-y0)*c+(0-z0)*s,(plate_depth-y0)*c+(0-z0)*s]
    b.require('section','Birdsmouth remaining section','profile_section',[pid],interval=seat,
              maximum_notch=maximum_notch,minimum_remaining=minimum_remaining,basis=notch_basis,
              plumb_top_start=h*s/c)
    if plate_ids:
        b.require('bearing','Birdsmouth bears on wall plate','minimum_total_contact',[pid,*plate_ids],minimum_area=t*plate_depth,normal=[0,0,-1])
    else:
        b.unverified('bearing','Rafter seat has no declared wall plate; bearing and connection remain unverified.')
    b.result.interfaces.update(run=run,pitch=pitch,overhang=overhang,plate_depth=plate_depth,
        top_at_ridge=bottom(run)+h/c,top_at_eave=bottom(y0)+h/c,
        seat_depth=cut,blank_length=length,rafter_thickness=t,rafter_depth=h)
    return b.commit()


def gable_roof(project, id, *, length, span, pitch, plate_depth,
               rafter_stock, ridge_stock, maximum_notch, minimum_remaining,
               notch_basis, system, frame=WallFrame(), spacing=16,
               eave_overhang=12, rake_overhang=0, plate_ids=((),()),
               tie_stock=None, ridge_support_ids=(), fascia_stock=None, span_table=None,
               soffit_stock=None, soffit_support_stock=None, soffit_thickness=.375,
               soffit_wall_ids=((),()), bird_box_stock=None, rake_fascia_stock=None,
               corner_trim_clearance=None, ridge_termination=None, eave_fascia_overlap=None,
               bird_box_return=0, fascia_assembly=None, assembly='Gable roof'):
    """Ridge runs local U; V spans the opposing outside wall faces.

    Supported systems are ridge_board_ties and structural_ridge. Rake overhang
    uses extended ridge/eave members and gable ladder lookouts. Roof covering,
    gable infill and ventilation remain separately declared enclosure work.
    """
    for v,n in ((length,'length'),(span,'span'),(pitch,'pitch'),(plate_depth,'plate_depth')):_number(v,n)
    for v,n in ((eave_overhang,'eave_overhang'),(rake_overhang,'rake_overhang')):_number(v,n,inclusive=True)
    if system not in ('ridge_board_ties','structural_ridge'):
        raise ValueError('Choose ridge_board_ties or structural_ridge explicitly')
    if len(plate_ids)!=2: raise ValueError('Provide plate IDs for the two eave walls')
    if soffit_stock and not fascia_stock: raise ValueError('Soffits require fascia stock')
    if bird_box_stock and (bird_box_stock not in project.stocks or not project.stocks[bird_box_stock].sheet):
        raise ValueError('Bird-box closures require sheet stock')
    _number(bird_box_return,'bird_box_return',inclusive=True)
    if eave_fascia_overlap is not None:_number(eave_fascia_overlap,'eave_fascia_overlap')
    if bird_box_return and (not soffit_stock or not rake_overhang):
        raise ValueError('Bird-box return requires closed eaves and rakes')
    trim_projection=trim_run=0
    if corner_trim_clearance is not None:
        if not isinstance(corner_trim_clearance,dict) or set(corner_trim_clearance)!={'projection','side_run'}:
            raise ValueError('Corner trim clearance needs projection and side_run')
        trim_projection=corner_trim_clearance['projection'];trim_run=corner_trim_clearance['side_run']
        _number(trim_projection,'trim projection');_number(trim_run,'trim side run')
        if not soffit_stock or not rake_overhang:raise ValueError('Corner trim clearance requires closed eaves and rakes')
        if 2*trim_run>=length or trim_projection>=min(rake_overhang,eave_overhang):
            raise ValueError('Corner trim clearance consumes the soffit')
    if soffit_stock and (len(soffit_wall_ids)!=2 or any(not ids for ids in soffit_wall_ids)):
        raise ValueError('Soffits require framing part IDs for both wall ledgers')
    if soffit_stock and any(pid not in {p['id'] for p in project.parts} for ids in soffit_wall_ids for pid in ids):
        raise ValueError('Unknown soffit wall framing part')
    if system=='ridge_board_ties' and not tie_stock: raise ValueError('A ridge-board roof requires tie stock')
    if system=='structural_ridge' and tie_stock: raise ValueError('Specify ties only for the ridge-board system')
    if ridge_termination is None:
        ridge_termination='wall' if system=='ridge_board_ties' and soffit_stock and rake_overhang else 'extended'
    if ridge_termination not in ('wall','extended'):raise ValueError('Ridge termination must be wall or extended')
    if ridge_termination=='wall' and system!='ridge_board_ties':
        raise ValueError('Wall-terminated overhang detail currently requires a ridge-board and tie system')
    t,h=section(project,rafter_stock);rt,rh=section(project,ridge_stock)
    run=(span-rt)/2
    if bird_box_return>=run:raise ValueError('Bird-box returns must stop before the ridge')
    if run<=plate_depth: raise ValueError('Roof span cannot accommodate plates and ridge')
    theta=math.atan(pitch/12);c=math.cos(theta);s=math.sin(theta);slope=pitch/12
    if rh+1e-8<h/c: raise ValueError('Ridge must cover the full plumb rafter depth')
    xs=positions(length,spacing,t)
    sizing=None
    if span_table is not None:
        if not isinstance(span_table,dict):raise ValueError('span_table must contain explicit lookup conditions')
        if any(right-left>spacing+1e-8 for left,right in zip(xs,xs[1:])):
            raise ValueError('Actual rafter bay exceeds span-table spacing; revise the layout')
        sizing=select_rafter_size(span=run-plate_depth,spacing=spacing,**span_table)
        if (t,h)!=sizing['section']:
            raise ValueError(f"Rafter stock must match span-table selection {sizing['nominal']} {sizing['section']}")
        if len(xs)<3:raise ValueError('Span table requires at least three braced rafter pairs')
    b=Builder(project,id,frame,'gable_roof',assembly)
    if sizing:
        b.result.interfaces['rafter_sizing']=sizing
        b.unverified('rafter_details', 'Rafter span-table lookup recorded; bearing capacity, notches, overhang loading and bracing installation require separate verification.')
    else:
        b.unverified('rafter_sizing', 'Rafter size is provisional: no applicable span-table lookup supplied. Establish site roof loads, species, grade, spacing and ceiling/roof system before selecting stock.')
    ridge_top=slope*(run-plate_depth)+h/c
    ridge_extension=rake_overhang if ridge_termination=='extended' else 0
    ridge=b.box('ridge',ridge_stock,(-ridge_extension,run,ridge_top-rh),(length+2*ridge_extension,rt,rh))
    if ridge_termination=='wall':
        b.require('ridge_termination','Ridge remains inside the gable walls','within_envelope',[ridge],
                  envelope=frame.box((0,run,ridge_top-rh),(length,rt,rh)))
    rafters=[]
    for i,x in enumerate(xs):
        pair=[]
        for side in (0,1):
            rf=WallFrame(frame.point(x,0 if side==0 else span,0),frame.angle,
                         frame.inward if side==0 else -frame.inward)
            rr=sawn_rafter(b.project,f'{id}.rafter.{i}.{side}',run=run,plate_depth=plate_depth,
                pitch=pitch,overhang=eave_overhang,stock=rafter_stock,maximum_notch=maximum_notch,
                minimum_remaining=minimum_remaining,notch_basis=notch_basis,frame=rf,
                plate_ids=plate_ids[side],assembly=assembly)
            pid=rr.roles['member'];pair.append(pid)
            if sizing:
                member=next(p for p in b.project.parts if p['id']==pid)
                member['span_table']=dict(sizing)
                member['note']+=f" Span selection: {sizing['table']}; clear horizontal span {sizing['required_span']} in <= {sizing['allowable_span']} in. {sizing['source']}"

            b.result.roles[f'rafter.{i}.{side}']=pid
            b.require(f'ridge_contact.{i}.{side}','Rafter plumb cut meets ridge','minimum_contact',
                      [pid,ridge],minimum_area=t*h/c)
        rafters.append(pair)
        if system=='ridge_board_ties':
            tie_t,tie_h=section(project,tie_stock)
            u=x+t if i<len(xs)-1 else x-tie_t
            if u<0 or u+tie_t>length: raise ValueError('Tie cannot fit next to its rafter pair')
            tie=b.box(f'tie.{i}',tie_stock,(u,0,0),(tie_t,span,tie_h))
            for side,pid in enumerate(pair):
                b.require(f'tie_contact.{i}.{side}','Tie meets rafter side','minimum_contact',
                          [tie,pid],minimum_area=plate_depth*min(tie_h,h-maximum_notch))
                if plate_ids[side]:
                    b.require(f'tie_bearing.{i}.{side}','Tie bears on plate','minimum_total_contact',
                              [tie,*plate_ids[side]],minimum_area=tie_t*plate_depth,normal=[0,0,-1])
    if system=='structural_ridge':
        if ridge_support_ids:
            for i,support in enumerate(ridge_support_ids):
                b.require(f'ridge_support.{i}','Structural ridge bearing','minimum_contact',
                          [ridge,support],minimum_area=rt*rt,normal=[0,0,-1])
        else: b.unverified('ridge_support','Structural ridge beam supports and their load path to foundation are not provided.')
    b.unverified('connections', 'Rafter/ridge capacity, uplift anchors, '+('tie fastening and thrust resistance' if system=='ridge_board_ties' else 'ridge support connection capacity')+' require the selected structural design.')
    if rake_overhang and not fascia_stock:
        raise ValueError('Rake overhang requires fascia stock for the ladder edge')
    # Eave fascia touches the rafter plumb tails. Its lower datum also owns the soffit.
    if fascia_stock:
        ft,fh=section(project,fascia_stock)
        fascia_blank=fh
        if eave_fascia_overlap is not None:
            fh=h/c+eave_fascia_overlap
            if fh>fascia_blank+.001:raise ValueError('Fascia blank must fit the rafter tail plus overlap')
        tail_top=slope*(-eave_overhang-plate_depth)+h/c
        if eave_overhang==0 and soffit_stock: raise ValueError('A soffit needs a positive eave overhang')
        fascias=[]
        for side,v in enumerate((-eave_overhang-ft,span+eave_overhang)):
            fascia=b.box(f'fascia.eave.{side}',fascia_stock,(-rake_overhang-(ft if rake_overhang else 0),v,tail_top-fh),(length+2*rake_overhang+(2*ft if rake_overhang else 0),ft,fascia_blank))
            b.project.parts[-1]['size'][2]=fh
            if fascia_assembly:b.project.parts[-1]['assembly']=fascia_assembly
            b.project.parts[-1]['profile']={'bottom':[0,0],'top':([fh-slope*ft,fh] if (side==0)==(frame.inward==1) else [fh,fh-slope*ft])}
            b.project.parts[-1]['blank_size']=[b.project.parts[-1]['size'][0],ft,fascia_blank]
            if eave_fascia_overlap is not None:
                b.require(f'fascia_tail_depth.{side}','Eave fascia covers rafter plumb tail plus overlap',
                          'face_alignment',[fascia,rafters[0][side]],axis=2,faces=['min','min'],offset=eave_fascia_overlap)
            fascias.append(fascia)
            for i,pair in enumerate(rafters):
                b.require(f'fascia_contact.{i}.{side}','Fascia meets rafter tail','minimum_contact',[fascia,pair[side]],minimum_area=t*min(fh,h/c-(slope*plate_depth if eave_overhang==0 else 0)))
        if rake_overhang:
            closed_rakes=bool(soffit_stock)
            rake_stock=rake_fascia_stock or fascia_stock
            rake_t,rake_blank=section(project,rake_stock)
            rake_depth=h+(soffit_thickness if closed_rakes else 0)
            if abs(rake_t-ft)>.001 or rake_blank<rake_depth-.001:
                raise ValueError('Rake fascia stock must match eave thickness and fit rafter plus soffit depth')
            if rake_overhang<=2*t:
                raise ValueError('Rake overhang must fit a single fly rafter, inner attachment rail and lookouts')
            if closed_rakes and eave_overhang<h*s:
                raise ValueError('Closed rake detail needs enough eave overhang for its sloping edge blocking')
            if closed_rakes:
                if soffit_stock not in project.stocks or not project.stocks[soffit_stock].sheet:
                    raise ValueError('Soffit requires sheet stock')
                _number(soffit_thickness,'soffit_thickness')
                sheet_w,sheet_l=sorted(project.stocks[soffit_stock].sheet)
                if rake_overhang>sheet_w:raise ValueError('Rake soffit width exceeds sheet width')
                if sheet_l<=soffit_thickness*s/c:raise ValueError('Rake soffit thickness exceeds sheet length')
                count=math.ceil((run/c)/(sheet_l-soffit_thickness*s/c))
                if run/count<3*t*c:
                    raise ValueError('Rake soffit panel cannot fit separate edge and middle blocking')
            else:count=1
            edge_run=span/2 if ridge_termination=='wall' else run
            if closed_rakes:
                count=math.ceil((edge_run/c)/(sheet_l-soffit_thickness*s/c))
            lookout_length=rake_overhang-2*t
            rake_fascias={}
            for end,u in enumerate((-rake_overhang-ft,length+rake_overhang)):
                for side in (0,1):
                    inward=frame.inward if side==0 else -frame.inward
                    side_frame=WallFrame(frame.point(0,0 if side==0 else span,0),frame.angle,inward)
                    rf=WallFrame(side_frame.point(u,0,0),frame.angle,inward)
                    fascia_id=_sloped_strip(b,f'fascia.rake.{end}.{side}',rake_stock,rf,
                        width=ft,y0=-eave_overhang,y1=span/2,top0=tail_top,
                        slope=slope,normal_depth=rake_depth,blank_depth=rake_blank)
                    if fascia_assembly:b.project.parts[-1]['assembly']=fascia_assembly
                    b.project.parts[-1]['note']=f'Rake fascia ripped to {rake_depth:g} in face: rafter depth plus soffit. Stock blank retained for takeoff.'
                    rake_fascias[end,side]=fascia_id
                    b.require(f'fascia_corner.{end}.{side}','Rake and eave fascia meet flush at the tail',
                              'minimum_contact',[fascia_id,fascias[side]],minimum_area=ft*min(fh,rake_depth/c))
                    zero=frame.point(0,0,0);along=frame.point(1,0,0)
                    b.require(f'fascia_flush.{end}.{side}','Eave fascia ends flush with the rake face',
                              'face_alignment',[fascia_id,fascias[side]],
                              direction=[a-z for a,z in zip(along,zero)],
                              faces=['min','min'] if end==0 else ['max','max'])
                    fly_u=-rake_overhang if end==0 else length+rake_overhang-t
                    fly_frame=WallFrame(side_frame.point(fly_u,0,0),frame.angle,inward)
                    fly=_sloped_strip(b,f'rafter.fly.{end}.{side}',rafter_stock,fly_frame,
                        width=t,y0=-eave_overhang,y1=edge_run,top0=tail_top,slope=slope,normal_depth=h)
                    if ridge_termination=='extended':
                        b.require(f'fly_ridge.{end}.{side}.0','Fly rafter meets extended ridge','minimum_contact',
                                  [fly,ridge],minimum_area=t*h/c)
                    origin=side_frame.point(0,0,0);up=side_frame.point(0,-s, c)
                    normal=[a-z for a,z in zip(up,origin)]
                    for label,face,offset in (('top','max',0),('bottom','min',h-rake_depth)):
                        b.require(f'fascia_depth.{end}.{side}.{label}',
                            'Rake fascia covers exactly the rafter and soffit depth','face_alignment',
                            [fly,fascia_id],direction=normal,faces=[face,face],offset=offset)
                    b.require(f'fly_fascia.{end}.{side}','Rake fascia meets outer fly rafter','minimum_contact',
                              [fly,fascia_id],minimum_area=(run+eave_overhang)*min(h,fh)/c)
                    host=rafters[0 if end==0 else -1][side]
                    back_u=-t if end==0 else length
                    backing=_sloped_strip(b,f'rafter.rake_backing.{end}.{side}',rafter_stock,
                        WallFrame(side_frame.point(back_u,0,0),frame.angle,inward),
                        width=t,y0=-eave_overhang,y1=edge_run,top0=tail_top,slope=slope,normal_depth=h)
                    b.require(f'rake_backing_host.{end}.{side}','Inner ladder rail doubles the main end rafter at attachment',
                              'minimum_contact',[backing,host],minimum_area=(run-plate_depth)*h/c)
                    host=backing
                    for panel_index in range(count):
                        ya=edge_run*panel_index/count;yb=edge_run*(panel_index+1)/count
                        bottom_centers=(ya+t*c/2,(ya+yb)/2,yb-t*c/2)
                        stations=tuple(v-h*s for v in bottom_centers) if closed_rakes else (plate_depth,run/2,run-h*s-t*c/2-.5)
                        blocks=[]
                        for local_j,v in enumerate(stations):
                            j=panel_index*3+local_j
                            z=slope*(v-plate_depth)+h/c
                            x=-rake_overhang+t if end==0 else length+t
                            lf=WallFrame(side_frame.point(x,0,0),frame.angle,inward)
                            center=lf.point(lookout_length/2,v+s*h/2,z-c*h/2)
                            block_id=f'{id}.lookout.{end}.{side}.{j}'
                            b.project.box(block_id,assembly,rafter_stock,(lookout_length,t,h),
                                (center[0]-lookout_length/2,center[1]-t/2,center[2]-h/2),
                                rotation=_tilted_rotation(lf.angle+(180 if lf.inward==-1 else 0),math.degrees(theta)))
                            b.register(f'lookout.{end}.{side}.{j}',b.project.parts[-1]);blocks.append(block_id)
                            b.require(f'lookout_host.{end}.{side}.{j}','Lookout meets inner rake framing','minimum_contact',
                                      [block_id,host],minimum_area=t*h)
                            b.require(f'lookout_edge.{end}.{side}.{j}','Lookout meets single outer fly rafter','minimum_contact',
                                      [block_id,fly],minimum_area=t*h)
                        if closed_rakes:
                            panel_u=-rake_overhang if end==0 else length
                            panel=_sloped_strip(b,f'soffit.rake.{end}.{side}.{panel_index}',soffit_stock,
                                WallFrame(side_frame.point(panel_u,0,0),frame.angle,inward),
                                width=rake_overhang,y0=ya,y1=yb,top0=slope*(ya-plate_depth),
                                slope=slope,normal_depth=soffit_thickness)
                            zero=side_frame.point(0,0,0);up=side_frame.point(0,-slope,1)
                            normal=[a-z for a,z in zip(up,zero)]
                            for k,support in enumerate([fly,backing]):
                                b.require(f'rake_soffit.rail.{end}.{side}.{panel_index}.{k}',
                                    'Rake soffit meets continuous edge framing','minimum_contact',
                                    [panel,support],minimum_area=t*(yb-ya)/c,normal=normal)
                            for k,block in enumerate(blocks):
                                b.require(f'rake_soffit.block.{end}.{side}.{panel_index}.{k}',
                                    'Rake soffit meets cross backing','minimum_contact',
                                    [panel,block],minimum_area=lookout_length*t,normal=normal)
                    if closed_rakes:
                        _bird_box(b,end,side,side_frame,length=length,span=span,rake=rake_overhang,
                                  eave=eave_overhang,plate_depth=plate_depth,slope=slope,c=c,
                                  tail_top=tail_top,fascia_thickness=ft,fascia_height=fh,rake_depth=rake_depth,
                                  rafter_depth=h,soffit_thickness=soffit_thickness,
                                  sheet_stock=soffit_stock,closure_stock=bird_box_stock or soffit_stock,
                                  support_stock=soffit_support_stock,
                                  trim_projection=trim_projection,return_run=bird_box_return,
                                  tapered=eave_fascia_overlap is not None,
                                  eave_fascia=fascias[side],rake_fascia=fascia_id)
                if ridge_termination=='wall':
                    b.require(f'fly_peak.{end}','Opposing fly rafters meet at the closed peak','minimum_contact',
                              [b.result.roles[f'rafter.fly.{end}.{side}'] for side in (0,1)],minimum_area=t*h/c)
                    if closed_rakes:
                        b.require(f'backing_peak.{end}','Inner overhang backing meets at peak','minimum_contact',
                                  [b.result.roles[f'rafter.rake_backing.{end}.{side}'] for side in (0,1)],minimum_area=t*h/c)
                        b.require(f'soffit_peak.{end}','Rake soffits close continuously at peak','minimum_contact',
                                  [b.result.roles[f'soffit.rake.{end}.{side}.{count-1}'] for side in (0,1)],minimum_area=rake_overhang*soffit_thickness/c)
                    b.unverified(f'peak_connection.{end}','Fly-rafter peak fastening/strap or angle connection and ladder attachment require the selected connection schedule; face contact alone does not verify joint capacity.')
                b.require(f'fascia_peak.{end}','Rake fascia boards meet at the peak','minimum_contact',
                          [rake_fascias[end,0],rake_fascias[end,1]],minimum_area=ft*rake_depth/c)
            b.result.interfaces['rake_fascia_depth']=rake_depth
            b.unverified('rake_connections','Rake ladder connection capacity, gable bracing and weather-edge flashing require the selected roof detail.')
            if not closed_rakes:
                b.unverified('rake_soffit','Rake ladder is open underneath; supply soffit stock and supports to generate rake soffits and bird-box returns.')
        if soffit_stock:
            if soffit_stock not in project.stocks or not project.stocks[soffit_stock].sheet:
                raise ValueError('Soffit requires sheet stock')
            _number(soffit_thickness,'soffit_thickness')
            if not soffit_support_stock:
                raise ValueError('Soffits require separate support stock')
            nt,nh=section(project,soffit_support_stock)
            if abs(nt-1.5)>.001 or nh<3.5-.001:
                raise ValueError('Soffit ledgers and joists require 2x dimensional lumber, at least actual 1.5 x 3.5 inches')
            if trim_projection>nt:raise ValueError('Corner trim projection exceeds the supported notch detail')
            if eave_fascia_overlap is None and fh<h/c+nh-.001:
                raise ValueError('Fascia must drop below the rafter tails enough for soffit supports')
            if eave_overhang<=nt: raise ValueError('Soffit depth must fit wall-side nailers')
            sheet_u=max(project.stocks[soffit_stock].sheet)
            if eave_overhang+ft>min(project.stocks[soffit_stock].sheet):
                raise ValueError('Soffit depth exceeds sheet width')
            for side in (0,1):
                z=tail_top-fh
                v=-nt if side==0 else span
                nailer=b.box(f'soffit.nailer.{side}',soffit_support_stock,(0,v,z),(length,nt,nh))
                b.require(f'soffit.ledger_section.{side}','Ledger uses 2x lumber on edge','minimum_section',
                          [nailer],thickness_axis=1,depth_axis=2,minimum_thickness=1.5,minimum_depth=nh,depth_direction=[0,0,1])
                zero=frame.point(0,0,0);toward=frame.point(0,1 if side==0 else -1,0)
                b.require(f'soffit.ledger_host.{side}','Soffit ledger connects to wall framing',
                          'minimum_total_contact',[nailer,*soffit_wall_ids[side]],
                          minimum_area=nh*min(t,nt),normal=[a-b for a,b in zip(toward,zero)])
                panel_count=math.ceil(length/sheet_u)
                panel_length=length/panel_count
                if panel_length<2*nt: raise ValueError('Soffit panel is too short for separate edge supports')
                u=0;i=0
                while i<panel_count:
                    end=length*(i+1)/panel_count
                    v=-eave_overhang-ft if side==0 else span
                    cut=trim_projection and (i==0 or i==panel_count-1)
                    if cut:
                        first=i==0;last=i==panel_count-1;p=trim_projection
                        if (trim_run if first else 0)+(trim_run if last else 0)>=end-u:
                            raise ValueError('Corner trim cuts consume an eave soffit panel')
                        points=[(u,-eave_overhang-ft),(end,-eave_overhang-ft),(end,-p if last else 0)]
                        if last:points.extend([(end-trim_run,-p),(end-trim_run,0)])
                        if first:points.extend([(u+trim_run,0),(u+trim_run,-p),(u,-p)])
                        else:points.append((u,0))
                        if side:points=[(x,span-y) for x,y in points]
                        pid=_plan_prism(b,f'soffit.panel.{side}.{i}',soffit_stock,frame,points,z-soffit_thickness,soffit_thickness)
                    else:
                        pid=b.box(f'soffit.panel.{side}.{i}',soffit_stock,(u,v,z-soffit_thickness),(end-u,eave_overhang+ft,soffit_thickness))
                    edge_supports=[nailer,fascias[side]]
                    for j,x in enumerate((u,end-nt)):
                        v0=-eave_overhang if side==0 else span+nt
                        role=f'soffit.block.{side}.{i}.{j}'
                        contact_depth=nh
                        if eave_fascia_overlap is not None:
                            sf=WallFrame(frame.point(0,0 if side==0 else span,0),frame.angle,
                                         frame.inward if side==0 else -frame.inward)
                            intervals=[(max(x,rx),min(x+nt,rx+t)) for rx in xs if rx<x+nt and rx+t>x]
                            out=_soffit_cleat(b,role,soffit_support_stock,sf,x,nt,-eave_overhang,-nt,z,nh,
                                             slope,plate_depth,intervals)
                            contact_depth=(nt-sum(e-a for a,e in intervals))*nh/nt+sum(e-a for a,e in intervals)*min(nh,eave_fascia_overlap)/nt
                            for k,rx in enumerate(xs):
                                overlap=max(0,min(x+nt,rx+t)-max(x,rx))
                                if overlap:
                                    contact_run=min(eave_overhang-nt,(nh-eave_fascia_overlap)/slope)
                                    if contact_run>0:
                                        b.require(f'{role}.rafter.{k}','Tapered soffit cleat meets the rafter underside',
                                                  'minimum_contact',[out,rafters[k][side]],minimum_area=overlap*contact_run/c)
                        else:
                            out=b.box(role,soffit_support_stock,(x,v0,z),(nt,eave_overhang-nt,nh))
                        edge_supports.append(out)
                        if eave_fascia_overlap is None:
                            b.require(f'soffit.joist_section.{side}.{i}.{j}','Soffit joist uses 2x lumber on edge',
                                      'minimum_section',[out],thickness_axis=0,depth_axis=2,
                                      minimum_thickness=1.5,minimum_depth=nh,depth_direction=[0,0,1])
                        for label,support in (('ledger',nailer),('fascia',fascias[side])):
                            b.require(f'soffit.block_connection.{side}.{i}.{j}.{label}',
                                      f'Soffit cleat meets {label}','minimum_contact',
                                      [out,support],minimum_area=nt*(contact_depth if label=='fascia' else nh))
                        if cut and ((i==0 and j==0) or (i==panel_count-1 and j==1)):
                            run=max(nt,trim_run)
                            if 2*nt+2*run>end-u:raise ValueError('Eave panel is too short for trim-notch backing')
                            bx=x+nt if j==0 else x-run
                            bv=-2*nt if side==0 else span+nt
                            backing=b.box(f'soffit.trim_backing.{side}.{i}.{j}',soffit_support_stock,
                                (bx,bv,z),(run,nt,nh))
                            edge_supports.append(backing)
                            for label,support,area in (('ledger',nailer,run*nh),('cross_member',out,nt*nh)):
                                b.require(f'soffit.trim_backing.{side}.{i}.{j}.{label}',
                                    'Trim-notch backing connects to soffit framing','minimum_contact',
                                    [backing,support],minimum_area=area)
                    b.require(f'soffit.support.{side}.{i}','Soffit attachment edges','panel_support',[pid,*edge_supports],
                              thickness_axis=0 if cut else 2,support_face='max',bearing_width=min(ft,.5))
                    u=end;i+=1
            b.result.interfaces['soffit_bottom']=frame.origin[2]+tail_top-fh-soffit_thickness
            b.result.interfaces.update(soffit_top=frame.origin[2]+tail_top-fh,soffit_nailer_depth=nh)
            if eave_fascia_overlap is not None:
                b.unverified('soffit_cleat_fastening','Scribed cleats retain 2x purchase blanks but taper at rafter tails. Attachment to rafters and fastening through the thin tail require a selected detail; these are not full-depth spanning joists.')
            b.unverified('soffit_attachment','Ledger/backing fasteners, support spacing/capacity and venting require the selected roof/enclosure detail; geometric framing contact is checked separately.')
    if ridge_termination=='extended' and soffit_stock and rake_overhang:
        b.unverified('ridge_enclosure','Extended ridge termination requires a designed enclosure at the gable peak; rake soffits stop at the ridge faces. Do not trim a structural ridge beam without its design detail.')
    b.unverified('gable_framing','Gable-end uprights are not supplied; add gable_end_frame with the end-wall caps.')
    b.unverified('enclosure','Roof sheathing/covering, weather edges and vented/unvented roof strategy remain separate enclosure assemblies.')
    b.unverified('gable_cladding','Gable-end sheathing and siding are not supplied; coordinate wall_enclosure with this roof.')
    b.result.interfaces.update(length=length,span=span,pitch=pitch,system=system,ridge_termination=ridge_termination,
                              eave_overhang=eave_overhang,rake_overhang=rake_overhang,
                              ridge_top=frame.origin[2]+ridge_top,plate_depth=plate_depth,
                              rafter_depth=h,ridge_depth=rh,ridge_thickness=rt,
                              soffit_thickness=soffit_thickness if soffit_stock else 0,
                              corner_trim_clearance=corner_trim_clearance,bird_box_return=bird_box_return,
                              eave_fascia_overlap=eave_fascia_overlap)
    return b.commit()


def _sloped_strip(builder,role,stock,frame,*,width,y0,y1,top0,slope,normal_depth,bottom_clip=None,blank_depth=None):
    """Plumb-cut sloped strip; width is U and normal_depth is stock thickness."""
    theta=math.atan(slope);c=math.cos(theta);s=math.sin(theta)
    bottom0=top0-normal_depth/c
    top1=top0+(y1-y0)*slope;bottom1=top1-normal_depth/c
    bottom_points=[(y0,max(bottom0,bottom_clip) if bottom_clip is not None else bottom0)]
    if bottom_clip is not None:
        crossing=y0+(bottom_clip-bottom0)/slope
        if y0<crossing<y1:bottom_points.append((crossing,bottom_clip))
    bottom_points.append((y1,max(bottom1,bottom_clip) if bottom_clip is not None else bottom1))
    if any(z>=top0+(y-y0)*slope for y,z in bottom_points):
        raise ValueError('Fascia bottom trim removes the entire section')
    points=[*bottom_points,(y1,top1),(y0,top0)]
    outline=[((y-y0)*c+(z-bottom0)*s,max(0,-(y-y0)*s+(z-bottom0)*c)) for y,z in points]
    size=(width,max(y for y,z in outline),blank_depth or normal_depth)
    center=frame.point(width/2,y0+size[1]/2*c-size[2]/2*s,
                       bottom0+size[1]/2*s+size[2]/2*c)
    pid=f'{builder.result.id}.{role}'
    builder.project.polygon_prism(pid,builder.assembly,stock,size,
        tuple(v-d/2 for v,d in zip(center,size)),outline,
        rotation=_tilted_rotation(frame.angle+(180 if frame.inward==-1 else 0),math.degrees(theta)))
    return builder.register(role,builder.project.parts[-1])


def _side_box(builder,role,stock,frame,origin,size):
    center=frame.point(*(o+d/2 for o,d in zip(origin,size)))
    pid=f'{builder.result.id}.{role}'
    builder.project.box(pid,builder.assembly,stock,size,
        tuple(v-d/2 for v,d in zip(center,size)),rotation=(0,0,frame.angle))
    return builder.register(role,builder.project.parts[-1])


def _side_prism(builder,role,stock,frame,u,width,points):
    """One sheet/board cut in a wall-local V/Z plane, mirrored consistently."""
    v0=min(v for v,z in points);v1=max(v for v,z in points)
    z0=min(z for v,z in points);z1=max(z for v,z in points)
    size=(width,v1-v0,z1-z0)
    center=frame.point(u+width/2,(v0+v1)/2,(z0+z1)/2)
    outline=[(v-v0 if frame.inward==1 else v1-v,z-z0) for v,z in points]
    pid=f'{builder.result.id}.{role}'
    builder.project.polygon_prism(pid,builder.assembly,stock,size,
        tuple(v-d/2 for v,d in zip(center,size)),outline,rotation=(0,0,frame.angle))
    return builder.register(role,builder.project.parts[-1])


def _plan_prism(builder,role,stock,frame,points,z,height):
    """Constant-thickness panel with its outline in the assembly U/V plane."""
    u0=min(u for u,v in points);u1=max(u for u,v in points)
    v0=min(v for u,v in points);v1=max(v for u,v in points)
    size=(height,u1-u0,v1-v0)
    center=frame.point((u0+u1)/2,(v0+v1)/2,z+height/2)
    outline=[(u-u0,v-v0 if frame.inward==1 else v1-v) for u,v in points]
    pid=f'{builder.result.id}.{role}'
    yaw=math.radians(frame.angle);sn,cs=math.sin(yaw),math.cos(yaw)
    if abs(cs)<1e-8:rotation=(0 if sn>0 else 180,-90 if sn>0 else 90,0)
    else:rotation=(math.degrees(math.atan2(-cs,0)),math.degrees(math.asin(-sn)),math.degrees(math.atan2(-cs,0)))
    builder.project.polygon_prism(pid,builder.assembly,stock,size,
        tuple(c-d/2 for c,d in zip(center,size)),outline,rotation=rotation)
    return builder.register(role,builder.project.parts[-1])


def _cleat_outline(v0,v1,z,height,slope,plate_depth,taper):
    if not taper:return [(v0,z),(v1,z),(v1,z+height),(v0,z+height)]
    top=lambda v:min(z+height,slope*(v-plate_depth))
    if top(v0)<=z:raise ValueError('Soffit cleat has no remaining tail depth')
    points=[(v0,z),(v1,z),(v1,top(v1))]
    crossing=(z+height)/slope+plate_depth
    if v0<crossing<v1:points.append((crossing,z+height))
    points.append((v0,top(v0)))
    return points


def _cleat_side_area(v0,v1,z,height,slope,plate_depth):
    points=_cleat_outline(v0,v1,z,height,slope,plate_depth,True)
    return abs(sum(a[0]*e[1]-e[0]*a[1] for a,e in zip(points,points[1:]+points[:1])))/2


def _soffit_cleat(b,role,stock,frame,u,width,v0,v1,z,height,slope,plate_depth,rafters,*,trim_projection=0,end=0):
    """One 2x blank, scribed only beneath actual rafters and around corner trim."""
    cuts={u,u+width,*[v for pair in rafters for v in pair]}
    if trim_projection:cuts.add(u+trim_projection if end else u+width-trim_projection)
    cuts=sorted(cuts);layers=[]
    for a,e in zip(cuts,cuts[1:]):
        mid=(a+e)/2
        clipped=trim_projection and (mid<u+trim_projection if end else mid>u+width-trim_projection)
        end_v=min(v1,-trim_projection) if clipped else v1
        taper=any(lo<=mid<=hi for lo,hi in rafters)
        points=_cleat_outline(v0,end_v,z,height,slope,plate_depth,taper)
        layers.append(dict(x=[a-u,e-u],outlines=[[(v-v0 if frame.inward==1 else v1-v,zz-z) for v,zz in points]]))
    size=(width,v1-v0,height);center=frame.point(u+width/2,(v0+v1)/2,z+height/2)
    pid=f'{b.result.id}.{role}'
    b.project.layered_prism(pid,b.assembly,stock,size,tuple(c-d/2 for c,d in zip(center,size)),layers,
        rotation=(0,0,frame.angle),note='Soffit cleat scribed beneath the rafter from a 2x blank; tail fastening is not a full-depth end joint.')
    return b.register(role,b.project.parts[-1])


def _bird_box(b,end,side,frame,*,length,span,rake,eave,plate_depth,slope,c,
              tail_top,fascia_thickness,fascia_height,rake_depth,rafter_depth,soffit_thickness,
              sheet_stock,closure_stock,support_stock,eave_fascia,rake_fascia,trim_projection=0,return_run=0,tapered=False):
    """Boxed eave return: flat base, plumb back, and slope-cut outer infill.

    Closure sheets use fascia thickness for a flush outside face and butt joints.
    The sloped rake fascia is clipped to this box's flat underside datum.
    """
    ft=fascia_thickness;fh=fascia_height;ss=soffit_thickness
    nt,nh=section(b.project,support_stock)
    if eave<=ft or rake<=nt:raise ValueError('Bird box must fit return panels and backing')
    z=tail_top-fh
    soffit_under=lambda v:slope*(v-plate_depth)-ss/c
    if soffit_under(-ft)<=z:raise ValueError('Bird box has no height below the rake soffit')
    outer_u=-rake-ft if end==0 else length+rake
    inner_u=-rake if end==0 else length
    prefix=f'bird_box.{end}.{side}'
    tip=max(-eave,-eave+(rake_depth/c-fh)/slope)
    supports=[eave_fascia,rake_fascia]
    if tip<0:
        top_at_tip=tail_top+slope*(tip+eave)-rake_depth/c
        points=[(tip,z),(return_run,z),(return_run,tail_top+slope*(eave+return_run)-rake_depth/c)]
        if top_at_tip>z+1e-8:points.append((tip,top_at_tip))
        face=_side_prism(b,f'{prefix}.face',closure_stock,frame,outer_u,ft,points)
        supports.append(face)
        b.require(f'{prefix}.face_joint','Bird-box infill meets rake fascia','minimum_contact',
                  [face,rake_fascia],minimum_area=ft*(return_run-tip)/c)
    back_u=-rake if end==0 else length+trim_projection if return_run else length
    back_width=rake-(trim_projection if return_run else 0)
    back=_side_prism(b,f'{prefix}.back',closure_stock,frame,back_u,back_width,
        [(return_run-ft,z),(return_run,z),(return_run,soffit_under(return_run)),(return_run-ft,soffit_under(return_run-ft))])
    supports.append(back)
    block_u=-nt if end==0 else length
    if tapered or return_run:
        block=_soffit_cleat(b,f'{prefix}.block',support_stock,frame,block_u,nt,-eave,return_run-ft,z,nh,
                            slope,plate_depth,[(block_u,block_u+nt)] if tapered else [],trim_projection=trim_projection,end=end)
    elif trim_projection:
        p=trim_projection
        points=[(-nt,-eave),(0,-eave),(0,-p),(-p,-p),(-p,-ft),(-nt,-ft)]
        if end:points=[(length-u,v) for u,v in points]
        block=_plan_prism(b,f'{prefix}.block',support_stock,frame,points,z,nh)
    else:
        block=_side_box(b,f'{prefix}.block',support_stock,frame,(block_u,-eave,z),(nt,eave-ft,nh))
    supports.append(block)
    if tapered:
        contact_run=min(eave+return_run-ft,(nh-(slope*(-eave-plate_depth)-z))/slope)
        if contact_run>0:
            b.require(f'{prefix}.rafter','Scribed bird-box cleat meets inner rake rail',
                      'minimum_contact',[block,b.result.roles[f'rafter.rake_backing.{end}.{side}']],minimum_area=nt*contact_run/c)
    if trim_projection:
        sister_u=block_u-nt if end==0 else block_u+nt
        sister=_side_box(b,f'{prefix}.block.sister',support_stock,frame,(sister_u,-eave,z),(nt,eave+return_run-ft,nh))
        supports.append(sister)
        b.require(f'{prefix}.trim_backing','Doubled bird-box backing supports the trim cutout','minimum_contact',
            [sister,block],minimum_area=_cleat_side_area(-eave,return_run-ft,z,nh,slope,plate_depth) if tapered else (eave-ft)*nh)
        for face in ('min','max'):
            b.require(f'{prefix}.block_depth.{face}','Scribed backing retains the full upright depth','face_alignment',
                [block,sister],axis=2,faces=[face,face])
    b.require(f'{prefix}.section','Bird-box backing uses 2x lumber on edge','minimum_section',
              [sister if trim_projection else block],thickness_axis=0,depth_axis=2,minimum_thickness=1.5,minimum_depth=nh,depth_direction=[0,0,1])
    for label,support in (('eave',eave_fascia),('back',back)):
        b.require(f'{prefix}.block_{label}','Bird-box backing meets its enclosure','minimum_contact',
                  [sister if trim_projection and label=='back' else block,support],
                  minimum_area=nt*(min(nh,slope*(-eave-plate_depth)-z) if tapered and label=='eave' else nh))
    if return_run:
        b.require(f'{prefix}.host','Bird-box cleat connects to the eave ledger','minimum_contact',
                  [block,f'{b.result.id}.soffit.nailer.{side}'],minimum_area=(nt-trim_projection)*nh)
    else:
        b.require(f'{prefix}.host','Bird-box return connects to the eave ledger','minimum_contact',
                  [back,f'{b.result.id}.soffit.nailer.{side}'],minimum_area=ft*nh)
    base_u=-rake-ft if end==0 else length
    if trim_projection:
        p=trim_projection
        points=[(-rake-ft,-eave-ft),(0,-eave-ft),(0,-p),(-p,-p),(-p,return_run),(-rake-ft,return_run)]
        if end:points=[(length-u,v) for u,v in points]
        panel=_plan_prism(b,f'{prefix}.soffit',sheet_stock,frame,points,z-ss,ss)
    else:
        panel=_side_box(b,f'{prefix}.soffit',sheet_stock,frame,
                        (base_u,-eave-ft,z-ss),(rake+ft,eave+ft+return_run,ss))
    b.require(f'{prefix}.support','Bird-box soffit has framing along all edges','panel_support',
              [panel,*supports],thickness_axis=0 if trim_projection else 2,support_face='max',bearing_width=min(ft,.5))


def gable_end_frame(project,id,*,roof,stud_stock,plate_ids,spacing=16,assembly='Gable end framing'):
    """2x4 uprights on gable caps, notched around end rafters and ties.

    Both end-wall cap scopes are required. Dimensions follow the roof frame.
    Notches describe fit only; allowable remaining section needs design review.
    """
    st,sd=section(project,stud_stock)
    if abs(st-1.5)>.001 or abs(sd-3.5)>.001:
        raise ValueError('Gable end framing requires actual 1.5 x 3.5 inch stock')
    if len(plate_ids)!=2 or any(not ids for ids in plate_ids):
        raise ValueError('Gable framing requires cap part IDs for both end walls')
    parts={p['id']:p for p in project.parts}
    if any(pid not in parts for ids in plate_ids for pid in ids):raise ValueError('Unknown gable wall cap')
    q=roof.interfaces;length=q['length'];span=q['span'];slope=q['pitch']/12;pd=q['plate_depth']
    _number(spacing,'spacing',minimum=st)
    rafter=parts[roof.roles['rafter.0.0']];rt,rh=section(project,rafter['stock'])
    ridge=parts[roof.roles['ridge']];ridge_t,ridge_h=section(project,ridge['stock'])
    run=(span-ridge_t)/2;c=1/math.sqrt(1+slope*slope)
    ridge_top=slope*(run-pd)+rh/c
    if length<=2*sd or rt>=sd:raise ValueError('Gable depth must fit inside the end-rafter arrangement')
    last=max(int(role.split('.')[1]) for role in roof.roles if role.startswith('rafter.') and len(role.split('.'))==3 and role.split('.')[1].isdigit())
    center=(span-st)/2
    ys=[y for y in positions(span,spacing,st) if y>=pd and y+st<=span-pd and (y+st<=(span-ridge_t)/2 or y>=(span+ridge_t)/2) and abs(y-center)>=st]
    ys=sorted([*ys,center])
    b=Builder(project,id,roof.frame,'gable_end_frame',assembly)
    for end in (0,1):
        x0=0 if end==0 else length-sd
        pair=[roof.roles[f'rafter.{0 if end==0 else last}.{side}'] for side in (0,1)]
        tie_id=roof.roles.get(f'tie.{0 if end==0 else last}')
        tie_interval=None;tie_h=0
        if tie_id:
            tie_t,tie_h=section(project,parts[tie_id]['stock'])
            tx=rt if end==0 else length-rt-tie_t
            tie_interval=(max(0,tx-x0),min(sd,tx+tie_t-x0))
            if tie_interval[1]<=tie_interval[0]:tie_interval=None
        for i,y in enumerate(ys):
            peak=abs(y-center)<.001
            side=0 if y<center else 1
            uphill=[y,y+st] if side==0 else [span-y,span-y-st]
            seat=[slope*(v-pd) for v in uphill]
            top=[ridge_top-ridge_h]*2 if peak else [v+rh/c for v in seat]
            breaks={0,sd}
            if not peak:breaks.add(rt if end==0 else sd-rt)
            if tie_interval:breaks.update(tie_interval)
            breaks=sorted(breaks);bands=[]
            for a,z in zip(breaks,breaks[1:]):
                middle=(a+z)/2
                behind_tie=tie_interval and tie_interval[0]<middle<tie_interval[1]
                under_rafter=not peak and (middle<rt if end==0 else middle>sd-rt)
                band_top=seat if under_rafter else top
                bottom=[tie_h if behind_tie else 0]*2
                bands.append(dict(x=[a,z],bottom=bottom,top=list(band_top)))
            if roof.frame.inward==-1:
                for band in bands:
                    band['bottom'].reverse();band['top'].reverse()
            height=max(top);size=(sd,st,height)
            center_world=roof.frame.point(x0+sd/2,y+st/2,height/2)
            pid=f'{id}.stud.{end}.{i}'
            b.project.banded_prism(pid,assembly,stud_stock,size,
                tuple(v-n/2 for v,n in zip(center_world,size)),bands,rotation=(0,0,roof.frame.angle),
                note='One 2x4 blank, slope cut and notched around the end rafter/tie. Notch capacity and fastening are unverified.')
            b.register(f'stud.{end}.{i}',b.project.parts[-1])
            foot=st*sum(band['x'][1]-band['x'][0] for band in bands if band['bottom']==[0,0])
            b.require(f'foot.{end}.{i}','Gable upright bears on wall caps','minimum_total_contact',
                      [pid,*plate_ids[end]],minimum_area=foot,normal=[0,0,-1])
            if peak:
                b.require(f'head.{end}.{i}','Peak upright meets ridge underside','minimum_contact',
                          [pid,roof.roles['ridge']],minimum_area=sd*min(st,ridge_t),normal=[0,0,1])
            else:
                zero=roof.frame.point(0,0,0)
                direction=roof.frame.point(-1 if end==0 else 1,0,0)
                # The upright's shoulder contacts the end rafter's inner face.
                # A tie rebate can remove the lower portion of that shoulder.
                low=[max(v,tie_h) if tie_interval else v for v in seat]
                shoulder=st*min(a-z for a,z in zip(top,low))
                b.require(f'shoulder.{end}.{i}','Notched upright meets end-rafter side','minimum_total_contact',
                          [pid,pair[side]],minimum_area=shoulder,normal=[a-z for a,z in zip(direction,zero)])
                direction=roof.frame.point(0,-slope if side==0 else slope,1)
                b.require(f'head.{end}.{i}','Notched upright meets rafter underside','minimum_total_contact',
                          [pid,pair[side]],minimum_area=rt*st/c,normal=[a-z for a,z in zip(direction,zero)])
            if tie_interval:
                b.require(f'tie_fit.{end}.{i}','Upright rebate fits over rafter tie','minimum_contact',
                          [pid,tie_id],minimum_area=st*(tie_interval[1]-tie_interval[0]),normal=[0,0,-1])
    b.unverified('notch_design','Gable stud notch depths, retained section, bracing, fastening and roof/wall capacity require the selected structural detail.')
    result=b.commit()
    project.validation['unverified']=[r for r in project.validation.get('unverified',[]) if r.get('rule')!=f'{roof.id}.gable_framing']
    result.interfaces.update(roof_id=roof.id,spacing=spacing,stud_stock=stud_stock)
    return result
