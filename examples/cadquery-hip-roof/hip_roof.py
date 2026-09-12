"""Project-owned equal-pitch hip recipe built from shared plane/stock operations."""
import math
import cadquery as cq
from stud.stock import Plane,StockParts,cut_member
from stud.roof_geometry import cut_panel
from stud.construction import imperial_model


def hip_roof(model, *, length=144,depth=96,slope=.5,overhang=8,wall_top=100):
    """A framing/roof-deck study, not a site-sized structural specification."""
    imperial_model(model)
    if not all(math.isfinite(v) for v in (length,depth,slope,overhang,wall_top)) or not length>depth>16 or not 0<slope<=1 or overhang<1.5:
        raise ValueError('Use length > depth > 16, a positive slope up to 1:1 and an overhang of at least 1.5 inches for this subfascia detail.')
    t,h,panel=1.5,5.5,.5;co=math.cos(math.atan(slope))
    z=wall_top+h/co-3.5*slope
    if length-depth<7 or depth/2*slope+h/co-3.5*slope-7.25<=0:
        raise ValueError('This fixture needs at least 7 inches of ridge length and adequate ridge clearance.')
    planes={'front':Plane.roof(origin=(0,0,z),slope=(0,slope)),
            'back':Plane.roof(origin=(0,depth,z),slope=(0,-slope)),
            'left':Plane.roof(origin=(0,0,z),slope=(slope,0)),
            'right':Plane.roof(origin=(length,0,z),slope=(-slope,0))}
    model.assembly('hip','Hip roof: plates, ridge board, hips, jacks and low ties')
    model.assembly('deck','Four roof planes over dropped hips')
    parts=[];deck=[];sheet_rows=[]
    stock=StockParts(model,parent='hip',demand_prefix='')
    seat_void=cq.Workplane('XY').box(length,depth,1000,centered=(False,False,False)).translate((0,0,wall_top-1000)).val()
    def add(pid,result,section,seat=False):
        shape,place,blank=result
        if seat:
            shape=shape.moved(place).cut(seat_void).moved(place.inverse)
            blank['operations'].append({'kind':'birdsmouth','frame':'building','footprint':[0,0,length,depth],
                'seat_z':wall_top,'description':'Remove material below the wall-top plane inside the framed footprint; retain the projecting tail.'})
        stock.add(pid,(shape,place,blank),section=section)
        model.requirement(pid+'.solid','solid_valid',[pid]);parts.append(pid)
        return pid
    def box(pid,size,origin,section,cut):
        return add(pid,(cq.Workplane('XY').box(*size,centered=(False,False,False)).val(),cq.Location(cq.Vector(*origin)),
                        {'size':list(size),'cut_length':cut,'operations':[{'kind':'square_cut','finished_length':cut}]}),section)
    plates={}
    for side,size,origin in [('front',(length,3.5,t),(0,0,wall_top-t)),('back',(length,3.5,t),(0,depth-3.5,wall_top-t)),
                             ('left',(3.5,depth-7,t),(0,3.5,wall_top-t)),('right',(3.5,depth-7,t),(length-3.5,3.5,wall_top-t))]:
        plates[side]=box('hip.plate.'+side,size,origin,(t,3.5),length if side in ('front','back') else depth-7)
    ridge_start,ridge_end=depth/2,length-depth/2
    ridge_z=planes['front'].height_at(ridge_start,depth/2)-slope*t/2
    ridge=add('hip.ridge',cut_member((ridge_start-t/2,depth/2,ridge_z),(ridge_end+t/2,depth/2,ridge_z),(t,7.25)),(t,7.25))
    # Drop square-edged hip stock so its top corners meet the roof planes.
    hip_ids=[]
    hip_drop=t*slope/(2*math.sqrt(2))
    for end,adjacent,xstart,xend in [('left','left',-overhang+t,ridge_start),('right','right',length+overhang-t,ridge_end)]:
        for side in ('front','back'):
            point,direction=planes[side].intersection(planes[adjacent]);point=cq.Vector(*point);direction=cq.Vector(*direction)
            at=lambda x:(point+direction*((x-point.x)/direction.x)-cq.Vector(0,0,hip_drop)).toTuple()
            normal=(1,0,0) if end=='left' else (-1,0,0)
            hip_end=xend-normal[0]*t/2
            upper=Plane((0,depth/2+(-t/2 if side=='front' else t/2),0),(0,1 if side=='front' else -1,0))
            tail=Plane((0,-overhang+t if side=='front' else depth+overhang-t,0),(0,-1 if side=='front' else 1,0))
            pid=add(f'hip.hip.{end}.{side}',cut_member(at(xstart),at(hip_end),(t,h),
                start_plane=Plane((xstart,0,0),tuple(-v for v in normal)),end_plane=Plane((hip_end,0,0),normal),
                top_planes=(upper,tail)),(t,h),seat=True)
            hip_ids.append(pid)
            model.requirement(pid+'.plate','support',[pid,plates[side]],threshold=.5,units='in2')
            station=ridge_start if (end=='left')==(side=='front') else ridge_end
            model.requirement(pid+'.common','contact',[pid,f'hip.rafter.{side}.at_{station:g}'],threshold=.5,units='in2')
    faces={
        'front':((0,0),(1,0),(0,1),length,[(-overhang,-overhang),(length+overhang,-overhang),(ridge_end,depth/2),(ridge_start,depth/2)]),
        'back':((length,depth),(-1,0),(0,-1),length,[(length+overhang,depth+overhang),(-overhang,depth+overhang),(ridge_start,depth/2),(ridge_end,depth/2)]),
        'left':((0,depth),(0,-1),(1,0),depth,[(-overhang,depth+overhang),(-overhang,-overhang),(ridge_start,depth/2)]),
        'right':((length,0),(0,1),(-1,0),depth,[(length+overhang,-overhang),(length+overhang,depth+overhang),(ridge_end,depth/2)])}
    # Commons end plumb at ridge faces; jacks end at offset hip side faces.
    # Separate these cases to preserve full-width commons without upper lips.
    frame_by_face={};boundaries={}
    for side,(base,u,v,extent,outline) in faces.items():
        plane=planes[side];caps=[]
        for other in planes:
            if other==side:continue
            intersection,_=plane.intersection(planes[other])
            # Comparing elevations yields the outward XY normal of this roof domain.
            sx=-plane.normal[0]/plane.normal[2]+planes[other].normal[0]/planes[other].normal[2]
            sy=-plane.normal[1]/plane.normal[2]+planes[other].normal[1]/planes[other].normal[2]
            caps.append((other,Plane(intersection,(sx,sy,0))))
        boundaries[side]=caps
        def position(station,run):
            x,y=base[0]+u[0]*station+v[0]*run,base[1]+u[1]*station+v[1]*run
            return (x,y,plane.height_at(x,y))
        common_stations=[ridge_start,ridge_end] if side in ('front','back') else [depth/2]
        stations=sorted(set(common_stations+[at for at in range(16,int(extent),16)
            if all(abs(at-common_at)>=t for common_at in common_stations)]));rafters=[]
        for station in stations:
            common=(ridge_start<=station<=ridge_end) if side in ('front','back') else station==depth/2
            member_caps=[(other,cap.offset(-t/2)) for other,cap in caps]
            if common:
                run=depth/2-t/2
                member_caps=[('ridge',Plane(position(station,run),(v[0],v[1],0)))]
            start=position(station,-overhang+t);ray=cq.Vector(v[0],v[1],plane.height_at(v[0],v[1])-plane.height_at(0,0))
            candidates=[(cq.Vector(*cap.normal).dot(cq.Vector(*cap.point)-cq.Vector(*start))/cq.Vector(*cap.normal).dot(ray),other,cap)
                        for other,cap in member_caps if cq.Vector(*cap.normal).dot(ray)>1e-8]
            distance,other,end_cap=min(candidates,key=lambda row:row[0]);end=(cq.Vector(*start)+ray*distance).toTuple()
            shape,place,blank=cut_member(start,end,(t,h),end_plane=end_cap,top_planes=(tuple(planes.values()) if common else (plane,))+tuple(cap for _,cap in member_caps))
            supports=hip_ids+[ridge]
            world=shape.moved(place)
            for support_id in supports:world=world.cut(model.shapes[support_id]['world'])
            blank['operations'].append({'kind':'scribe_cut','frame':'building','supports':supports,
                'description':'Trim residual interference against the finite supports after the explicit ridge/hip face cuts.'})
            pid=add(f'hip.rafter.{side}.at_{station:g}',(world.moved(place.inverse),place,blank),(t,h),seat=True)
            rafters.append(pid);model.requirement(pid+'.plate','support',[pid,plates[side]],threshold=t*3.5-.001,units='in2')
            support=ridge if common or {side,other}=={'front','back'} else f'hip.hip.{other if other in ("left","right") else side}.{side if side in ("front","back") else other}'
            model.requirement(pid+'.end','contact',[pid,support],threshold=.5,units='in2')
        # Continuous plumb subfascia outside the shortened rafter tails.
        # Keep the outer eave datum; bevel only the top and miter the corners.
        run=-overhang+t/2
        top=plane.height_at(*position(0,-overhang+t)[:2])
        start=list(position(-overhang,run));end=list(position(extent+overhang,run))
        start[2]=end[2]=top
        first=next(cap for _,cap in caps if cap.normal[0]*u[0]+cap.normal[1]*u[1]<-1e-8)
        last=next(cap for _,cap in caps if cap.normal[0]*u[0]+cap.normal[1]*u[1]>1e-8)
        fascia_depth=h/co+.125  # Plumb tail depth plus a small lower reveal.
        fascia_stock=next(size for size in (7.25,9.25) if size>=fascia_depth)
        bottom=Plane((0,0,top-fascia_depth),(0,0,-1))
        fascia=add(f'hip.subfascia.{side}',cut_member(start,end,(t,fascia_stock),start_plane=first,end_plane=last,
                    top_planes=(plane,bottom)),(t,fascia_stock))
        for pid in rafters:
            model.requirement(pid+'.tail','contact',[pid,fascia],threshold=t*h/co-.001,units='in2')
        frame_by_face[side]=rafters+[fascia]+hip_ids+[ridge]
        # Clip each plane's footprint into strips whose seams fall on rafter centers.
        def coordinate(p):return (p[0]-base[0])*u[0]+(p[1]-base[1])*u[1]
        def clip(poly,limit,greater):
            result=[]
            for a,b in zip(poly,poly[1:]+poly[:1]):
                va,vb=coordinate(a)-limit,coordinate(b)-limit
                inside_a=va>=-1e-8 if greater else va<=1e-8;inside_b=vb>=-1e-8 if greater else vb<=1e-8
                if inside_a:result.append(a)
                if inside_a!=inside_b:
                    t_=va/(va-vb);result.append((a[0]+t_*(b[0]-a[0]),a[1]+t_*(b[1]-a[1])))
            return result
        # Keep seams off the three-member ridge/hip junction; use the next jack.
        seams=list(range(32,int(extent),32))
        if side in ('front','back'):
            seams=[at+16 if min(abs(at-ridge_start),abs(at-ridge_end))<t and at+16<extent else at for at in seams]
        edges=[-overhang]+sorted(set(seams))+[extent+overhang]
        for index,(a,b) in enumerate(zip(edges,edges[1:])):
            poly=clip(clip(outline,a+(.0625 if index else 0),True),b-(.0625 if index<len(edges)-2 else 0),False)
            if len(poly)<3:continue
            shape,place,blank=cut_panel(plane,poly,panel,x_direction=(u[0],u[1],0))
            pid=f'deck.{side}.{index}';model.part(pid,shape,parent='deck',location=place,blank=blank,material='panel.roof',color='#c8b183')
            model.requirement(pid+'.blank','stock_fit',[pid]);model.requirement(pid+'.edges','panel_edge_support',[pid]+frame_by_face[side],threshold=0,direction_local=[0,0,-1],explanation='Strict coplanar backing check: dropped square-edged hips provide edge contact, so hip seams are expected to be flagged; verify the sheathing edge and fastening detail separately.');deck.append(pid)
            sheet_rows.append({'id':pid+'.sheet','size':[48,96],'kerf':.125,'panels':[{'object_id':pid,'origin':[0,0],'size':blank['size'][:2],
                'operations':blank['operations'],'supported_edges':{'framing':frame_by_face[side]},'edge_requirement':pid+'.edges'}]})
    # Low ties alongside common rafters; end ties frame into the cross ties.
    cross_ties={}
    for pid in list(parts):
        if not pid.startswith('hip.rafter.front.at_'):continue
        station=float(pid.rsplit('_',1)[1]);x=station+t/2
        tie=box(f'hip.tie.cross.at_{station:g}',(t,depth,3.5),(x,0,wall_top),(t,3.5),depth)
        cross_ties[station]=tie
        for side,at in [('front',station),('back',length-station)]:
            model.requirement(tie+'.'+side,'contact',[tie,f'hip.rafter.{side}.at_{at:g}'],threshold=.5,units='in2')
    for end,stations in [('left',sorted(at for at in cross_ties if at<=ridge_start)),
                         ('right',sorted(at for at in cross_ties if at>=ridge_end))]:
        edges=([0]+[at+1.5*t for at in stations[:-1]]) if end=='left' else [at+1.5*t for at in stations]
        stops=([at+t/2 for at in stations]) if end=='left' else [at+t/2 for at in stations[1:]]+[length]
        for index,(start,stop) in enumerate(zip(edges,stops)):
            tie=box(f'hip.tie.end.{end}.{index}',(stop-start,t,3.5),(start,depth/2+t/2,wall_top),(t,3.5),stop-start)
            if (end=='left' and index==0) or (end=='right' and index==len(edges)-1):
                model.requirement(tie+'.common','contact',[tie,f'hip.rafter.{end}.at_{depth/2:g}'],threshold=.5,units='in2')
            for at in stations:
                if abs(start-(at+1.5*t))<1e-8 or abs(stop-(at+t/2))<1e-8:
                    model.requirement(tie+f'.cross.{at:g}','contact',[tie,cross_ties[at]],threshold=t*3.5-.001,units='in2')
    stock.purchase(stock_lengths=[96,120,144,192],kerf=.125,material='softwood, fixture sizes')
    model.demand('deck.sheets',product_id='panel.roof',specification={'material':'plywood','thickness':panel,'sheet':[48,96]},object_ids=deck,purchase_unit='sheet',sheets=sheet_rows)
    model.requirement('hip.interference','collision_free',parts+deck,threshold=0,units='in3')
    model.connection('hip.design',parts=parts,description='Compose four roof planes, a ridge board with low cross and hip-end ties, dropped square-edged hip members, common/jack rafters and plumb continuous subfascia.',
        unresolved=['Conventional tied ridge-board layout. Tie sections are fixture sizes, not load-sized. Design rafter-to-tie fasteners and all segmented hip-end tie-to-cross-tie connections for a continuous tension path; verify continuity, wall bracing, hip reactions, bearing/notch limits and uplift connections.'])
    model.connection('deck.fix',parts=deck,description='Install the individually cut roof sheets with seams over rafters and perimeter support from hips, ridge and continuous subfascia.',
        unresolved=['The dropped, unbacked hips support sheathing at their outer top edges; the strict continuous coplanar panel-edge checks flag the hip seams. Verify this sheathing edge and fastening detail. Select sheathing grade, spans, fasteners, edge gaps and diaphragm details for the project.'])
    model.step('hip.frame','Set ridge board and hips, fit rafters with footprint seat cuts, and install plumb continuous subfascia.',parts=parts,connections=['hip.design'])
    model.step('deck.install','Cut the four roof-plane sheet layouts and install on the checked framing.',parts=deck,connections=['deck.fix'],prerequisites=['hip.frame'])
    model.drawing('hip.plan',objects=parts,direction=(0,0,1),up=(0,1,0))
    model.notes.append('Composable hip-roof study: framing and roof deck only. This is a geometry/fabrication fixture, not a site-specific construction design. Roof covering, hip/ridge caps, fascia, soffits, ventilation and enclosure remain project-owned finish work.')
    return {'planes':planes,'parts':parts,'panels':deck,'hips':hip_ids,'ridge':ridge}
