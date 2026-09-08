"""Asphalt finish envelopes on the authoritative gable roof planes.

Courses represent exposed coverage, not hidden shingle headlaps. Installation
requirements remain explicit; appearance geometry is never a fastening design.
"""
import math
from ._assembly import Builder, section
from .assemblies import WallFrame, _number
from .roofs import _sloped_strip

SOURCE = 'https://www.gaf.com/en-us/document-library/documents/installation-instructions-&-guides/timberline-layerlock-installation-instructions-trilingual-restl622.pdf'


def asphalt_roof(project, id, *, roof, deck_stock, membrane_stock, shingle_stock,
                 flashing_stock, starter_stock, cap_stock, deck_thickness=.625,
                 exposure=5.625, shingle_width=39.375, overhang=.5,
                 assembly='Asphalt roof finish'):
    """Standard-slope (>=4:12) gable finish with a closed, capped ridge.

    Stock for finishes uses net coverage, including hidden laps in its purchase
    yield. Metal, starter and cap stock use linear coverage.
    Deck edges are nominal joints; panel edge support and installation gaps are
    explicitly unverified. No penetrations, valleys or ridge vent are implied.
    """
    q=roof.interfaces
    if q['pitch']<4:raise ValueError('This assembly requires pitch >=4:12; low-slope underlayment needs a separate detail')
    for value,name in ((deck_thickness,'deck thickness'),(exposure,'exposure'),(shingle_width,'shingle width'),(overhang,'overhang')):
        _number(value,name)
    if not .25<=overhang<=.75:raise ValueError('Shingle overhang must be 1/4–3/4 inch')
    if deck_thickness<.375:raise ValueError('Deck must be at least 3/8 inch; span rating still requires verification')
    for key in (deck_stock,membrane_stock,shingle_stock,flashing_stock,starter_stock,cap_stock):
        if key not in project.stocks:raise ValueError(f'Unknown stock: {key}')
    if exposure>shingle_width/2:raise ValueError('Exposure must be at most half the shingle width')
    ds=project.stocks[deck_stock]
    if not ds.sheet or ds.sheet_thickness!=deck_thickness:raise ValueError('Deck stock must declare matching sheet thickness')
    for key in (membrane_stock,shingle_stock):
        if not project.stocks[key].coverage_sq_ft:raise ValueError('Finish stocks require net coverage purchase yields')
    for key in (flashing_stock,starter_stock,cap_stock):
        if not project.stocks[key].coverage_linear_ft:raise ValueError('Edge, starter and cap stocks require linear coverage yields')
    source_parts={p['id']:p for p in project.parts}
    if any(pid not in source_parts for pid in roof.part_ids):raise ValueError('Roof members missing')
    ft=section(project,source_parts[roof.roles['fascia.eave.0']]['stock'])[0] if 'fascia.eave.0' in roof.roles else 0
    # A square fascia would intersect the deck outside the rafter tail.
    for side in (0,1):
        fascia=source_parts.get(roof.roles.get(f'fascia.eave.{side}'))
        if fascia and 'profile' not in fascia:raise ValueError('Eave fascia must be beveled to the roof plane')
    slope=q['pitch']/12;c=1/math.sqrt(1+slope*slope)
    x0=-q['rake_overhang']-(ft if q['rake_overhang'] else 0)
    x1=q['length']-x0;y0=-q['eave_overhang']-ft;y1=q['span']/2
    if x1-x0<12 or (y1-y0)/c<12:raise ValueError('Roof planes must fit the six-inch starter and cap envelopes')
    base=lambda y:slope*(y-q['plate_depth'])+q['rafter_depth']/c
    b=Builder(project,id,roof.frame,'asphalt_roof',assembly)
    def plane(role,stock,side,a,z,lo,hi,bottom,thickness):
        sf=WallFrame(roof.frame.point(a,0 if side==0 else q['span'],0),roof.frame.angle,
                     roof.frame.inward if side==0 else -roof.frame.inward)
        pid=_sloped_strip(b,role,stock,sf,width=z-a,y0=lo,y1=hi,
            top0=base(lo)+(bottom+thickness)/c,slope=slope,normal_depth=thickness)
        part=b.project.parts[-1]
        if role.startswith('cap.'):part['coverage_length_in']=(z-a)/2
        elif role.startswith('starter.'):part['coverage_length_in']=(z-a)*(hi-lo)/c/6
        elif role.startswith('drip.'):part['coverage_length_in']=(hi-lo)/c
        return pid
    def contact(role,pid,hosts,area):
        zero=roof.frame.point(0,0,0);point=roof.frame.point(0,slope if side==0 else -slope,-1)
        b.require(role,'Roof layer contacts its substrate','minimum_total_contact',[pid,*hosts],minimum_area=area,normal=[a-z for a,z in zip(point,zero)])
    for side in (0,1):
        deck=[]
        # Strength axis across rafters; choose seams on regular rafter centers.
        rt=section(project,source_parts[roof.roles[f'rafter.0.{side}']]['stock'])[0]
        centers=[]
        for role,pid in roof.roles.items():
            bits=role.split('.')
            if len(bits)==3 and bits[0]=='rafter' and bits[1].isdigit() and bits[2]==str(side):
                index=int(bits[1]);centers.append((index,pid))
        # Recover actual stations in roof coordinates, including rotated frames.
        origin=roof.frame.point(0,0,0);u=roof.frame.point(1,0,0)
        stations=[]
        for _,pid in sorted(centers):
            part=source_parts[pid];center=[o+d/2 for o,d in zip(part['origin'],part['size'])]
            stations.append(sum((v-o)*(a-o) for v,o,a in zip(center,origin,u)))
        seams=[x0];limit=max(ds.sheet)
        for station in stations:
            if station-seams[-1]>limit:
                eligible=[v for v in stations if seams[-1]<v<=seams[-1]+limit]
                if not eligible:raise ValueError('Rafter stations cannot support available deck sheet length')
                seams.append(max(eligible))
        while x1-seams[-1]>limit:
            eligible=[v for v in stations if seams[-1]<v<=seams[-1]+limit]
            if not eligible:raise ValueError('Deck end span exceeds sheet length')
            seams.append(max(eligible))
        seams.append(x1)
        usable_slope_length=min(ds.sheet)-deck_thickness*slope
        if usable_slope_length<=0:raise ValueError('Deck sheet is too narrow for the plumb edge bevel')
        rows=math.ceil((y1-y0)/c/usable_slope_length)
        for i,(a,z) in enumerate(zip(seams,seams[1:])):
            for j in range(rows):
                lo=y0+(y1-y0)*j/rows;hi=y0+(y1-y0)*(j+1)/rows
                pid=plane(f'deck.{side}.{i}.{j}',deck_stock,side,a,z,lo,hi,0,deck_thickness);deck.append(pid)
                contact(f'deck_bearing.{side}.{i}.{j}',pid,roof.part_ids,(hi-lo)/c*.5)
        # Continuous membrane envelope; lap details are an installation requirement.
        membrane=plane(f'membrane.{side}',membrane_stock,side,x0,x1,y0,y1,deck_thickness,.06)
        contact(f'membrane_bearing.{side}',membrane,deck,(x1-x0)*(y1-y0)/c*.99)
        # Flashing apron below membrane at eave; roof flange represented by the
        # membrane boundary, with apron separately visible outside the deck.
        sf=WallFrame(roof.frame.point(x0,0 if side==0 else q['span'],0),roof.frame.angle,
                     roof.frame.inward if side==0 else -roof.frame.inward)
        from .roofs import _side_box
        apron=_side_box(b,f'drip.eave.{side}',flashing_stock,sf,(0,y0-.025,base(y0)-1.5),(x1-x0,.025,1.5+deck_thickness/c))
        b.project.parts[-1]['coverage_length_in']=x1-x0
        # Rake apron follows the slope; flange/laps are installation envelopes.
        for end,x in enumerate((x0-.025,x1)):
            plane(f'drip.rake.{side}.{end}',flashing_stock,side,x,x+.025,y0,y1,-1.5,1.5+deck_thickness+.06)
        # Starter perimeter and field are distinct net-area envelopes. Rake strips
        # stop at the eave starter so there is no double-counted corner footprint.
        low=y0-overhang*c;left=x0-overhang;right=x1+overhang
        starter=plane(f'starter.eave.{side}',starter_stock,side,left,right,low,low+6*c,deck_thickness+.06,.08)
        contact(f'starter_bearing.eave.{side}',starter,[membrane],(x1-x0)*(6-overhang)*.99)
        for end,a in enumerate((left,right-6)):
            strip=plane(f'starter.rake.{side}.{end}',starter_stock,side,a,a+6,low+6*c,y1,deck_thickness+.06,.08)
            contact(f'starter_bearing.rake.{side}.{end}',strip,[membrane],(6-overhang)*(y1-low-6*c)/c*.99)
        count=math.ceil((y1-low)/c/exposure)
        field=[]
        for row in range(count):
            lo=low+row*exposure*c;hi=min(y1,lo+exposure*c)
            start=left-(row%4)*6
            col=0
            while start<right:
                a=max(left,start);z=min(right,start+shingle_width)
                if z>a:
                    us=sorted({a,z,*[v for v in (left+6,right-6) if a<v<z]})
                    vs=sorted({lo,hi,*[v for v in (low+6*c,) if lo<v<hi]})
                    for ui,(u0,u1) in enumerate(zip(us,us[1:])):
                        for vi,(v0,v1) in enumerate(zip(vs,vs[1:])):
                            perimeter=v0<low+6*c-.001 or u0<left+6-.001 or u1>right-6+.001
                            bottom=deck_thickness+(.14 if perimeter else .06)
                            pid=plane(f'shingle.{side}.{row}.{col}.{ui}.{vi}',shingle_stock,side,u0,u1,v0,v1,bottom,deck_thickness+.32-bottom)
                            b.project.parts[-1]['note']='Exposed shingle coverage; concealed headlaps included in stock yield. 6 inch course offset. '+SOURCE
                            color=project.stocks[shingle_stock].color
                            if len(color)==7 and color.startswith('#'):
                                try:
                                    factor=.88+((row*17+col*29+side*7)%7)*.035
                                    b.project.parts[-1]['color']='#'+''.join(f'{min(255,round(int(color[i:i+2],16)*factor)):02x}' for i in (1,3,5))
                                except ValueError:pass
                            field.append(pid)
                            hosts=[p['id'] for p in b.project.parts if p['role'].startswith(f'starter.') and p['role'].split('.')[2]==str(side)] if perimeter else [membrane]
                            # Overhanging starter edges are supported inboard.
                            contact(f'field_bearing.{side}.{row}.{col}.{ui}.{vi}',pid,hosts,(u1-u0)*(v1-v0)/c*.9)
                start+=shingle_width;col+=1
        for k,a in enumerate(range(math.floor(left/6),math.ceil(right/6))):
            lo=max(left,a*6);hi=min(right,(a+1)*6)
            if hi>lo:
                cap=plane(f'cap.{side}.{k}',cap_stock,side,lo,hi,y1-6*c,y1,deck_thickness+.32,.18)
                contact(f'cap_bearing.{side}.{k}',cap,field,(hi-lo)*6*.99)
    b.unverified('deck_installation','Deck span rating, strength axis, joint staggering, 1/8 inch installation gaps, panel-edge blocking/clips and fastening require the selected panel detail. Bearing checks do not verify all edges.')
    b.unverified('weather_installation','Finish parts are net-coverage envelopes: concealed shingle headlaps, membrane laps, metal roof flanges/hemming and corner laps are not fabricated solids. Install eave metal under membrane, rake metal above it, and starter at both edges per product instructions. '+SOURCE)
    b.unverified('site_roof','Closed ridge shown. Ventilation/condensation design, ice-barrier extent, product compatibility, fastening and wind sealing require project-specific selections; roofing dead load must be included in rafter sizing.')
    b.result.interfaces.update(roof_id=roof.id,deck_thickness=deck_thickness,exposure=exposure,
        shingle_overhang=overhang,net_field_sq_ft=2*(x1-x0+2*overhang)*(y1-y0+overhang*c)/c/144,
        ridge_length=x1-x0+2*overhang,source=SOURCE,representation='net exposed coverage; concealed laps not modeled')
    result=b.commit()
    project.validation['unverified']=[r for r in project.validation['unverified'] if r.get('rule')!=f'{roof.id}.enclosure']
    return result
