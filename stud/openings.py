"""Door/window products, separate from rough-opening construction framing."""
from .assemblies import FramedOpening, _number
from ._assembly import Builder


def _unit(project,id,opening,stock,frame_depth,inset,gap,assembly,builder):
    if not isinstance(opening,FramedOpening) or not opening.dimensions:
        raise ValueError('Unit requires a framed opening with dimensional interfaces')
    if stock not in project.stocks or not project.stocks[stock].product:
        raise ValueError('Unit requires stock registered with product=True')
    _number(frame_depth,'frame_depth');_number(gap,'installation_gap',inclusive=True)
    _number(abs(inset),'inset magnitude',inclusive=True)
    q=opening.dimensions
    if inset>0 or inset+frame_depth<q['wall_depth']:
        raise ValueError('Unit frame must span the host framing depth; use exterior/interior extensions for finished-wall reveals')
    u,z=q['start']+gap,q['bottom']+gap
    w,h=q['width']-2*gap,q['height']-2*gap
    if min(w,h)<=0: raise ValueError('Installation gap consumes the rough opening')
    b=Builder(project,id,opening.frame,builder,assembly)
    return b,(u,z,w,h)


def _product(b,role,stock,origin,size,color=None,opacity=None):
    pid=b.box(role,stock,origin,size)
    part=b.project.parts[-1];part['purchase_component']=b.result.id
    if color: part['color']=color
    if opacity is not None: part['opacity']=opacity
    return pid


def _sill_support(b,opening,stock,support_ids,u,z,w,gap,unit_parts):
    """Continuous installation packer over the host wall's bearing depth.

    Projecting product noses remain subject to the manufacturer's support detail.
    The packer is an installation material, not another purchased door/window.
    """
    if stock is None:
        if support_ids: raise ValueError('Sill support IDs require sill_support_stock')
        b.unverified('sill_bearing','Unit sill bearing is not modeled; specify installation support material and host support IDs.')
        return
    if stock not in b.project.stocks or not b.project.stocks[stock].sheet:
        raise ValueError('Sill support requires sheet stock')
    ids=list(dict.fromkeys(support_ids))
    if not ids or any(pid not in {p['id'] for p in b.target.parts} for pid in ids):
        raise ValueError('Sill support requires existing host support IDs')
    if gap<=0: raise ValueError('Sill packer requires a positive installation gap')
    depth=opening.dimensions['wall_depth']
    packer=b.box('sill_support',stock,(u,0,z-gap),(w,depth,gap))
    b.require('sill_support.bearing','Sill packer bears on the host assembly',
        'minimum_total_contact',[packer,*ids],normal=[0,0,-1],minimum_area=w*depth)
    for role,pid,width in unit_parts:
        b.require(f'sill_support.{role}','Unit sill/jamb bears on installation packer',
            'minimum_contact',[pid,packer],normal=[0,0,-1],minimum_area=width*depth)
    b.result.interfaces.update(sill_support=packer,sill_support_ids=ids,sill_bearing_depth=depth)
    b.unverified('sill_installation','Sill packer checks bearing across the host wall depth only. Material suitability, projecting threshold/sill support, anchorage and pan flashing must follow the selected unit.')


def _finish(b,opening,stock,u,z,w,h,inset,frame_depth,external_ids):
    ids=b.result.part_ids
    # Depth is the product's installation envelope; U/Z retain rough-opening fit.
    q=opening.dimensions
    b.require('installation','Product fits rough opening and declared wall-depth envelope','within_envelope',ids,
        envelope=opening.frame.box((q['start'],inset,q['bottom']),(q['width'],frame_depth,q['height'])))
    base=opening.frame.point(0,0,0);inside=opening.frame.point(0,1,0)
    b.require('host_depth','Unit spans host wall depth','host_depth',ids,
        origin=base,direction=[x-y for x,y in zip(inside,base)],depth=q['wall_depth'])
    b.result.interfaces.update(unit_width=w,unit_height=h,frame_depth=frame_depth,
        exterior_plane=opening.frame.point(0,inset,0),interior_plane=opening.frame.point(0,inset+frame_depth,0),
        opening_id=opening.id,product_stock=stock)
    b.unverified('product_detail','Generic product geometry: verify manufacturer dimensions, attachment, flashing, seals and required usable opening. Rough-opening size is not net clear egress.')
    return b.commit()


def door_unit(project,id,*,opening,product_stock,frame_depth,hand='left',swing='in',
              inset=0,installation_gap=.5,jamb_thickness=.75,leaf_thickness=1.75,
              reveal=.125,threshold_height=.75,open_angles=(30,60,90),
              obstacle_ids=(),sill_support_stock=None,sill_support_ids=(),assembly='Door unit'):
    """Generic prehung unit; handedness is as viewed in wall-local U/V.

    A left hinge is at minimum U. Inward swing moves into positive wall-local V.
    open_angles are selected states, not a continuous motion certification.
    Include nearby wall finishes and other obstructions in obstacle_ids.
    """
    b,(u,z,w,h)=_unit(project,id,opening,product_stock,frame_depth,inset,installation_gap,assembly,'door_unit')
    for v,n in ((jamb_thickness,'jamb_thickness'),(leaf_thickness,'leaf_thickness'),(reveal,'reveal'),(threshold_height,'threshold_height')):_number(v,n)
    if hand not in ('left','right') or swing not in ('in','out'):raise ValueError('Choose left/right hand and in/out swing')
    if frame_depth<leaf_thickness or w<=2*(jamb_thickness+reveal) or h<=jamb_thickness+threshold_height+2*reveal:
        raise ValueError('Door components do not fit the unit envelope')
    jt=jamb_thickness
    for side,x in [('left',u),('right',u+w-jt)]:_product(b,f'jamb.{side}',product_stock,(x,inset,z),(jt,frame_depth,h),'#d8cdb7')
    _product(b,'head',product_stock,(u+jt,inset,z+h-jt),(w-2*jt,frame_depth,jt),'#d8cdb7')
    _product(b,'threshold',product_stock,(u+jt,inset,z),(w-2*jt,frame_depth,threshold_height),'#596064')
    x=u+jt+reveal;bottom=z+threshold_height+reveal
    leaf_w=w-2*(jt+reveal);leaf_h=h-jt-threshold_height-2*reveal
    v=inset+frame_depth-leaf_thickness if swing=='in' else inset
    leaf=_product(b,'leaf',product_stock,(x,v,bottom),(leaf_w,leaf_thickness,leaf_h))
    pivot=opening.frame.point(x if hand=='left' else x+leaf_w,
                              inset+frame_depth if swing=='in' else inset,bottom)
    sign=(1 if hand=='left' else -1)*(1 if swing=='in' else -1)*opening.frame.inward
    obstacles=list(dict.fromkeys([pid for pid in b.result.part_ids if pid!=leaf]+list(obstacle_ids)))
    for i,angle in enumerate(open_angles):
        _number(angle,'open angle',inclusive=True)
        if angle>180:raise ValueError('Open angle must be at most 180 degrees')
        b.require(f'open.{i}',f'Door clearance at {angle:g} degrees','motion_clearance',
                  [leaf,*obstacles],moving_parts=[leaf],motion=dict(kind='rotate_z',pivot=pivot,angle=sign*angle))
    b.result.interfaces.update(hand=hand,swing=swing,hinge=pivot,leaf_width=leaf_w,leaf_height=leaf_h,
                              moving_parts=[leaf],open_angles=list(open_angles))
    _sill_support(b,opening,sill_support_stock,sill_support_ids,u,z,w,installation_gap,
        [('threshold',b.result.roles['threshold'],w-2*jt),
         ('left',b.result.roles['jamb.left'],jt),('right',b.result.roles['jamb.right'],jt)])
    b.unverified('sweep','Door states are sampled; continuous swing, handles, hinges and landing/access requirements remain to verify.')
    return _finish(b,opening,product_stock,u,z,w,h,inset,frame_depth,obstacle_ids)


def window_unit(project,id,*,opening,product_stock,frame_depth,operation='casement',
                hand='left',inset=0,installation_gap=.5,frame_thickness=1,
                sash_depth=1.5,rail_width=1.5,reveal=.125,open_angles=(30,60,90),
                slide_fraction=.8,obstacle_ids=(),sill_support_stock=None,sill_support_ids=(),assembly='Window unit'):
    """Generic fixed, outward-casement or two-track horizontal-slider unit."""
    b,(u,z,w,h)=_unit(project,id,opening,product_stock,frame_depth,inset,installation_gap,assembly,'window_unit')
    for v,n in ((frame_thickness,'frame_thickness'),(sash_depth,'sash_depth'),(rail_width,'rail_width'),(reveal,'reveal')):_number(v,n)
    if operation not in ('fixed','casement','slider') or hand not in ('left','right'):
        raise ValueError('Supported window operations: fixed, casement, slider; hand: left or right')
    ft=frame_thickness
    if w<=2*(ft+rail_width+reveal) or h<=2*(ft+rail_width+reveal):raise ValueError('Window rails consume the glazing opening')
    if sash_depth>frame_depth:raise ValueError('Sash depth exceeds frame depth')
    for side,x in [('left',u),('right',u+w-ft)]:_product(b,f'frame.{side}',product_stock,(x,inset,z),(ft,frame_depth,h),'#ded8cc')
    for side,height in [('sill',z),('head',z+h-ft)]:_product(b,f'frame.{side}',product_stock,(u+ft,inset,height),(w-2*ft,frame_depth,ft),'#ded8cc')
    x=u+ft+reveal;bottom=z+ft+reveal
    iw=w-2*(ft+reveal);ih=h-2*(ft+reveal)
    def sash(name,a,v,width):
        if width<=2*rail_width:raise ValueError('Sash is too narrow for its rails')
        ids=[]
        for side,sx in [('left',a),('right',a+width-rail_width)]:
            ids.append(_product(b,f'{name}.{side}',product_stock,(sx,v,bottom),(rail_width,sash_depth,ih),'#e7e3da'))
        for side,sz in [('bottom',bottom),('top',bottom+ih-rail_width)]:
            ids.append(_product(b,f'{name}.{side}',product_stock,(a+rail_width,v,sz),(width-2*rail_width,sash_depth,rail_width),'#e7e3da'))
        ids.append(_product(b,f'{name}.glazing',product_stock,
            (a+rail_width,v+sash_depth/2-.0625,bottom+rail_width),(width-2*rail_width,.125,ih-2*rail_width),'#9ec7ce',.4))
        return ids
    if operation=='slider':
        if frame_depth<2*sash_depth+reveal:raise ValueError('Slider needs two separated sash tracks')
        _number(slide_fraction,'slide_fraction',inclusive=True)
        if slide_fraction>1:raise ValueError('slide_fraction must be between 0 and 1')
        left=sash('sash.left',x,inset,iw/2)
        right=sash('sash.right',x+iw/2,inset+sash_depth+reveal,iw/2)
        moving=left if hand=='left' else right
        a=opening.frame.point(0,0,0);c=opening.frame.point((1 if hand=='left' else -1)*iw/2*slide_fraction,0,0)
        motion=dict(kind='translate',offset=[v-u for v,u in zip(c,a)])
        obstacles=[pid for pid in b.result.part_ids if pid not in moving]+list(obstacle_ids)
        b.require('open.slider','Slider clearance in selected open state','motion_clearance',
            list(dict.fromkeys(moving+obstacles)),moving_parts=moving,motion=motion)
    else:
        moving=sash('sash',x,inset,iw)
        if operation=='casement':
            pivot=opening.frame.point(x if hand=='left' else x+iw,inset,bottom)
            sign=(-1 if hand=='left' else 1)*opening.frame.inward
            obstacles=[pid for pid in b.result.part_ids if pid not in moving]+list(obstacle_ids)
            for i,angle in enumerate(open_angles):
                _number(angle,'open angle',inclusive=True)
                if angle>180:raise ValueError('Open angle must be at most 180 degrees')
                b.require(f'open.{i}',f'Casement clearance at {angle:g} degrees','motion_clearance',
                    list(dict.fromkeys(moving+obstacles)),moving_parts=moving,motion=dict(kind='rotate_z',pivot=pivot,angle=sign*angle))
        else: moving=[]
    b.result.interfaces.update(operation=operation,hand=hand,moving_parts=moving)
    _sill_support(b,opening,sill_support_stock,sill_support_ids,u,z,w,installation_gap,
        [('sill',b.result.roles['frame.sill'],w-2*ft),
         ('left',b.result.roles['frame.left'],ft),('right',b.result.roles['frame.right'],ft)])
    if operation!='fixed':b.unverified('sweep','Window operating states are sampled; hardware, continuous travel and manufacturer net opening remain to verify.')
    return _finish(b,opening,product_stock,u,z,w,h,inset,frame_depth,obstacle_ids)
