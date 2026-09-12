"""Project-owned equal-pitch hip recipe built from shared plane/stock operations."""
import math
import cadquery as cq
from stud.stock import Plane,StockParts,cut_member
from stud.roof_geometry import cut_panel
from stud.construction import imperial_model


def hip_roof(model, *, length=144,depth=96,slope=.5,overhang=8,wall_top=100):
    """A framing/roof-deck study, not a site-sized structural specification."""
    imperial_model(model)
    if not all(math.isfinite(v) for v in (length,depth,slope,overhang,wall_top)) or not length>depth>16 or not 0<slope<=1 or overhang<0:
        raise ValueError('Use length > depth > 16, a positive slope up to 1:1 and nonnegative overhang.')
    t,h,panel=1.5,5.5,.5;co=math.cos(math.atan(slope))
    z=wall_top+h/co-3.5*slope
    if length-depth<7 or depth/2*slope+h/co-3.5*slope-7.25<=0:
        raise ValueError('This fixture needs at least 7 inches of ridge length and positive ridge-post height.')
    planes={'front':Plane.roof(origin=(0,0,z),slope=(0,slope)),
            'back':Plane.roof(origin=(0,depth,z),slope=(0,-slope)),
            'left':Plane.roof(origin=(0,0,z),slope=(slope,0)),
            'right':Plane.roof(origin=(length,0,z),slope=(-slope,0))}
    model.assembly('hip','Hip roof: plates, ridge supports, hips and jacks')
    model.assembly('deck','Four roof planes with supported sheet cuts')
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
    ridge_z=planes['front'].height_at(ridge_start,depth/2)
    ridge=add('hip.ridge',cut_member((ridge_start,depth/2,ridge_z),(ridge_end,depth/2,ridge_z),(t,7.25),
                                   top_planes=(planes['front'],planes['back'])),(t,7.25))
    for end,x in [('left',ridge_start),('right',ridge_end-3.5)]:
        height=ridge_z-7.25-wall_top
        post=box('hip.ridge_post.'+end,(3.5,3.5,height),(x,depth/2-1.75,wall_top),(3.5,3.5),height)
        model.requirement(post+'.bearing','support',[ridge,post],threshold=3.5*t,units='in2')
    # Plane intersections define the hip axes. Their stock is backed to both faces.
    hip_ids=[]
    for end,adjacent,xstart,xend in [('left','left',-overhang,ridge_start),('right','right',length+overhang,ridge_end)]:
        for side in ('front','back'):
            point,direction=planes[side].intersection(planes[adjacent]);point=cq.Vector(*point);direction=cq.Vector(*direction)
            at=lambda x:(point+direction*((x-point.x)/direction.x)).toTuple()
            normal=(1,0,0) if end=='left' else (-1,0,0)
            upper=Plane((0,depth/2,0),(0,1 if side=='front' else -1,0))
            tail=Plane((0,-overhang if side=='front' else depth+overhang,0),(0,-1 if side=='front' else 1,0))
            pid=add(f'hip.hip.{end}.{side}',cut_member(at(xstart),at(xend),(t,h),
                start_plane=Plane((xstart,0,0),tuple(-v for v in normal)),end_plane=Plane((xend,0,0),normal),
                top_planes=(planes[side],planes[adjacent],upper,tail)),(t,h),seat=True)
            hip_ids.append(pid)
            model.requirement(pid+'.plate','support',[pid,plates[side]],threshold=.5,units='in2')
            model.requirement(pid+'.ridge','contact',[pid,ridge],threshold=.5,units='in2')
    faces={
        'front':((0,0),(1,0),(0,1),length,[(-overhang,-overhang),(length+overhang,-overhang),(ridge_end,depth/2),(ridge_start,depth/2)]),
        'back':((length,depth),(-1,0),(0,-1),length,[(length+overhang,depth+overhang),(-overhang,depth+overhang),(ridge_start,depth/2),(ridge_end,depth/2)]),
        'left':((0,depth),(0,-1),(1,0),depth,[(-overhang,depth+overhang),(-overhang,-overhang),(ridge_start,depth/2)]),
        'right':((length,0),(0,1),(-1,0),depth,[(length+overhang,-overhang),(length+overhang,depth+overhang),(ridge_end,depth/2)])}
    # Shrink each plane's domain to the side faces of the hip/ridge members.
    frame_by_face={};boundaries={}
    for side,(base,u,v,extent,outline) in faces.items():
        plane=planes[side];caps=[]
        for other in planes:
            if other==side:continue
            intersection,_=plane.intersection(planes[other])
            # Comparing elevations yields the outward XY normal of this roof domain.
            sx=-plane.normal[0]/plane.normal[2]+planes[other].normal[0]/planes[other].normal[2]
            sy=-plane.normal[1]/plane.normal[2]+planes[other].normal[1]/planes[other].normal[2]
            caps.append((other,Plane(intersection,(sx,sy,0)).offset(-t/2)))
        boundaries[side]=caps
        def position(station,run):
            x,y=base[0]+u[0]*station+v[0]*run,base[1]+u[1]*station+v[1]*run
            return (x,y,plane.height_at(x,y))
        stations=list(range(16,int(extent),16));rafters=[]
        for station in stations:
            start=position(station,-overhang);ray=cq.Vector(v[0],v[1],plane.height_at(v[0],v[1])-plane.height_at(0,0))
            candidates=[(cq.Vector(*cap.normal).dot(cq.Vector(*cap.point)-cq.Vector(*start))/cq.Vector(*cap.normal).dot(ray),other,cap)
                        for other,cap in caps if cq.Vector(*cap.normal).dot(ray)>1e-8]
            distance,other,end_cap=min(candidates,key=lambda row:row[0]);end=(cq.Vector(*start)+ray*distance).toTuple()
            pid=add(f'hip.rafter.{side}.at_{station}',cut_member(start,end,(t,h),end_plane=end_cap,top_planes=(plane,)+tuple(cap for _,cap in caps)),(t,h),seat=True)
            rafters.append(pid);model.requirement(pid+'.plate','support',[pid,plates[side]],threshold=t*3.5-.001,units='in2')
            support=ridge if {side,other}=={'front','back'} else f'hip.hip.{other if other in ("left","right") else side}.{side if side in ("front","back") else other}'
            model.requirement(pid+'.end','contact',[pid,support],threshold=.5,units='in2')
        # Eave edge blocks terminate against adjacent rafters or the hip side faces.
        blocks=[];intervals=list(zip([-overhang]+[at+t/2 for at in stations],[at-t/2 for at in stations]+[extent+overhang]))
        run=-overhang+t/2*co
        for index,(lo,hi) in enumerate(intervals):
            first=Plane(position(lo,run),(-u[0],-u[1],0));last=Plane(position(hi,run),(u[0],u[1],0))
            if index==0:first=next(cap for _,cap in caps if cap.normal[0]*u[0]+cap.normal[1]*u[1]<-1e-8)
            if index==len(intervals)-1:last=next(cap for _,cap in caps if cap.normal[0]*u[0]+cap.normal[1]*u[1]>1e-8)
            def at_cap(cap):
                p0=cq.Vector(*position(0,run));axis=cq.Vector(u[0],u[1],0)
                station=cq.Vector(*cap.normal).dot(cq.Vector(*cap.point)-p0)/cq.Vector(*cap.normal).dot(axis)
                return position(station,run)
            pid=add(f'hip.eave.{side}.{index}',cut_member(at_cap(first),at_cap(last),(t,3.5),start_plane=first,end_plane=last,up=plane.normal,
                                                        top_planes=(plane,)+tuple(cap for _,cap in caps)),(t,3.5))
            blocks.append(pid)
        frame_by_face[side]=rafters+blocks+hip_ids+[ridge]
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
            model.requirement(pid+'.blank','stock_fit',[pid]);model.requirement(pid+'.edges','panel_edge_support',[pid]+frame_by_face[side],threshold=0,direction_local=[0,0,-1]);deck.append(pid)
            sheet_rows.append({'id':pid+'.sheet','size':[48,96],'kerf':.125,'panels':[{'object_id':pid,'origin':[0,0],'size':blank['size'][:2],
                'operations':blank['operations'],'supported_edges':{'framing':frame_by_face[side]},'edge_requirement':pid+'.edges'}]})
    stock.purchase(stock_lengths=[96,120,144,192],kerf=.125,material='softwood, fixture sizes')
    model.demand('deck.sheets',product_id='panel.roof',specification={'material':'plywood','thickness':panel,'sheet':[48,96]},object_ids=deck,purchase_unit='sheet',sheets=sheet_rows)
    model.requirement('hip.interference','collision_free',parts+deck,threshold=0,units='in3')
    model.connection('hip.design',parts=parts,description='Compose four roof planes, a supported ridge, backed hip members, common/jack rafters and eave backing.',
        unresolved=['Fixture member sections are not load-sized. Specify ridge-post support to foundation, wall bracing, hip/ridge reactions, bearing/notch limits, uplift and all connection schedules for a real building.'])
    model.connection('deck.fix',parts=deck,description='Install the individually cut roof sheets with seams over rafters and perimeter support from hips, ridge and eave blocks.',
        unresolved=['Select sheathing grade, spans, fasteners, edge gaps and diaphragm details for the project.'])
    model.step('hip.frame','Set supported ridge and hips, fit rafters with footprint seat cuts, and install eave backing.',parts=parts,connections=['hip.design'])
    model.step('deck.install','Cut the four roof-plane sheet layouts and install on the checked framing.',parts=deck,connections=['deck.fix'],prerequisites=['hip.frame'])
    model.drawing('hip.plan',objects=parts,direction=(0,0,1),up=(0,1,0))
    model.notes.append('Composable hip-roof study: framing and roof deck only. This is a geometry/fabrication fixture, not a site-specific construction design. Roof covering, hip/ridge caps, fascia, soffits, ventilation and enclosure remain project-owned finish work.')
    return {'planes':planes,'parts':parts,'panels':deck,'hips':hip_ids,'ridge':ridge}
