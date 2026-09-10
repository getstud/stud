"""Compact workshop packets: reusable cut labels and shared drawing sheets."""
from collections import defaultdict
from copy import deepcopy
from html import escape
import io
import json
import math
from types import SimpleNamespace

import cadquery as cq
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.platypus import Paragraph, Table, TableStyle

from .contracts import StudError, atomic_write, digest
from .evaluated import object_scope
from .units import defaults as unit_defaults
from .plans import Packet, crop_bounds, format_length, operation_text, ordered_steps, project_vector, view_basis


def normalized(value):
    if isinstance(value,bool):return value
    if isinstance(value,(int,float)):return round(value,6)
    if isinstance(value,dict):return {k:normalized(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [normalized(v) for v in value]
    return value


def cut_groups(model,demands=None):
    """Group the same fabrication recipe only when native finished solids agree."""
    volume_tolerance=unit_defaults(model.units)['query_tolerance']**3
    candidates=defaultdict(list);groups=[];labels={}
    all_demands=list(demands) if demands is not None else list(getattr(model,'demands',{}).values())
    for obj in model.objects.values():
        applicable=[d for d in all_demands if obj['id'] in d['object_ids'] and d['product_id']==obj.get('material')]
        materials=sorted({digest(normalized(dict(product_id=d['product_id'],specification=d['specification']))) for d in applicable})
        signature=digest(normalized(dict(material=obj.get('material'),material_specifications=materials,blank=obj.get('blank'))))
        group=None
        for candidate in candidates[signature]:
            first=model.shapes[candidate['objects'][0]]['local'];second=model.shapes[obj['id']]['local']
            # Coincident shape frames and recipes can differ by floating-point
            # noise. Native symmetric subtraction rejects a hidden local edit.
            if abs(first.Volume()-second.Volume())<volume_tolerance and first.cut(second).Volume()<volume_tolerance and second.cut(first).Volume()<volume_tolerance:
                group=candidate;break
        if group is None:
            group=dict(label=f'C{len(groups)+1:02d}',objects=[],blank=obj.get('blank') or {},material=obj.get('material'),example=obj['label'],material_keys=materials)
            candidates[signature].append(group);groups.append(group)
        group['objects'].append(obj['id']);labels[obj['id']]=group['label']
    return groups,labels


class CompactPacket(Packet):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.groups,self.labels=cut_groups(self.model,self.manifest['demands'])
        self.group_by_label={group['label']:group for group in self.groups}
        self.materials={};self.demand_material={}
        for demand in self.manifest['demands']:
            key=digest(normalized(dict(product_id=demand['product_id'],specification=demand['specification'])))
            if key not in self.materials:self.materials[key]=dict(label=f'M{len(self.materials)+1:02d}',product_id=demand['product_id'],specification=demand['specification'])
            self.demand_material[demand['id']]=self.materials[key]['label']
        self.current_y=None;self.page_open=False
        self.view_sheets={}
        self.inventory={'cuts':self.groups,'materials':list(self.materials.values()),'boards':[],'sheets':[],'steps':[]}

    @property
    def body_width(self):return self.width-2*self.margin

    @property
    def body_top(self):return self.height-self.margin-72

    def new_page(self,title,kind,**details):
        if self.page_open:self.footer()
        self.header(title,kind,**details);self.page_open=True;self.current_y=self.body_top

    def close_page(self):
        if self.page_open:self.footer()
        self.page_open=False;self.current_y=None

    def text(self,text,*,title='Workshop notes',kind='notes',bold=False):
        style=deepcopy(self.text_style)
        if bold:style.fontName='Helvetica-Bold'
        paragraph=Paragraph(escape(str(text)),style)
        _,height=paragraph.wrap(self.body_width,self.height)
        if self.current_y is None or self.current_y-height<self.margin+60:
            self.new_page(title,kind)
        if height>self.body_top-self.margin-60:raise StudError('plan_layout','A packet paragraph exceeds one page.')
        paragraph.drawOn(self.canvas,self.margin,self.current_y-height);self.current_y-=height+6

    def flow_table(self,title,headers,rows,widths,kind):
        if not rows:return
        self.text(title,title=title,kind=kind,bold=True)
        data=[[Paragraph(escape(str(cell)),self.cell_style) for cell in headers]]+[
            [Paragraph(escape(str(cell)),self.cell_style) for cell in row] for row in rows]
        table=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8eee9')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),
            ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
            ('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#87968b')),
            ('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#ced7d0'))]))
        tables=[table]
        while tables:
            current=tables.pop(0);available=self.current_y-self.margin-60
            _,height=current.wrap(self.body_width,available)
            if height>available:
                pieces=current.split(self.body_width,available)
                if len(pieces)<2:
                    if abs(self.current_y-self.body_top)<1:
                        raise StudError('plan_layout',f'A {title} row is too tall for one page.')
                    self.new_page(title,kind);tables.insert(0,current);continue
                current=pieces[0];tables=pieces[1:]+tables
                _,height=current.wrap(self.body_width,available)
            current.drawOn(self.canvas,self.margin,self.current_y-height);self.current_y-=height+10
            if tables:self.new_page(title+' — continued',kind)

    def drawings(self,views):
        # Drawing scale changes to fit; annotation type stays readable. Details
        # retain a full page when their larger scale needs the available area.
        groups=[]
        for view in views:
            if view.get('scale') or self.spec.get('scale'):
                groups.append([view])
            elif groups and len(groups[-1])<4 and not groups[-1][0].get('scale') and groups[-1][0].get('sheet_group')==view.get('sheet_group'):
                groups[-1].append(view)
            else:groups.append([view])
        self.view_sheets={view['id']:index+1 for index,group in enumerate(groups) for view in group}
        for group in groups:
            self.new_page('Construction drawings','drawing',views=[])
            available=self.body_top-self.margin-72
            columns=2 if len(group)>2 else 1;rows=math.ceil(len(group)/columns)
            gap=18;panel_height=(available-gap*(rows-1))/rows;panel_width=(self.body_width-gap*(columns-1))/columns
            for index,view in enumerate(group):
                row,column=divmod(index,columns)
                self.view_panel(view,self.margin+column*(panel_width+gap),self.body_top-(row+1)*panel_height-row*gap,panel_width,panel_height)
            if len(self.pages[-1]['views'])==1:
                self.pages[-1].update(self.pages[-1]['views'][0])
            self.current_y=self.margin+62
        self.close_page()

    def view_panel(self,view,x,y,width,height):
        c=self.canvas;right,up,_=view_basis(view)
        ids=object_scope(self.model,view.get('objects'));crop=crop_bounds(view)
        points=[]
        for pid in ids:
            box=self.model.shapes[pid]['world'].BoundingBox()
            points.extend((cq.Vector(px,py,pz).dot(right),cq.Vector(px,py,pz).dot(up))
                for px in (box.xmin,box.xmax) for py in (box.ymin,box.ymax) for pz in (box.zmin,box.zmax))
        bounds=crop or [min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
        dimensions=[self.review['dimensions'][key] for key in view['dimensions'] if key in self.review['dimensions']]
        vertical=sum(abs((cq.Vector(*d['end_point'])-cq.Vector(*d['start_point'])).dot(up))>
                     abs((cq.Vector(*d['end_point'])-cq.Vector(*d['start_point'])).dot(right)) for d in dimensions)
        horizontal=len(dimensions)-vertical
        left=14+vertical*18;bottom=16+horizontal*18;top=30;gutter=52
        aw=width-left-gutter;ah=height-top-bottom
        if min(aw,ah)<20:
            raise StudError('plan_layout','The dimensions need more room; split this view or use the expanded layout.')
        required=max((bounds[2]-bounds[0])*self.points_per_unit/aw,(bounds[3]-bounds[1])*self.points_per_unit/ah)
        scale=view.get('scale',self.spec.get('scale'))
        if scale is None:scale=next((n for n in (1,2,5,10,15,20,25,30,40,50,75,100,150,200,500,1000) if n>=required),None)
        if scale is None or scale<required-1e-9:raise StudError('plan_layout','The requested scale needs a larger sheet or expanded packet layout.')
        drawing,projection=project_vector(self.model,view,float(scale))
        dx=x+left+(aw-drawing.width)/2;dy=y+bottom+(ah-drawing.height)/2
        c.setFillColor(colors.HexColor('#25372f'));c.setFont('Helvetica-Bold',9)
        c.drawString(x,y+height-10,view['label'])
        c.setFont('Helvetica',8)
        parent=(' · detail of sheet '+str(self.view_sheets.get(view['detail_of'],'not included'))) if view.get('detail_of') else ''
        c.drawString(x,y+height-22,f'1:{scale:g} · {self.units}'+parent)
        c.saveState()
        if crop:
            clip=c.beginPath();clip.rect(dx,dy,drawing.width,drawing.height);c.clipPath(clip,stroke=0,fill=0)
        renderPDF.draw(drawing,c,dx,dy);c.restoreState()
        if crop:
            c.saveState();c.setDash(2,3);c.setStrokeColor(colors.HexColor('#87968b'));c.rect(dx,dy,drawing.width,drawing.height,stroke=1,fill=0);c.restoreState()
        factor=projection['factor'];xmin,ymin=projection['bounds']['min'];basis=projection['basis']
        matrix=[[factor*v for v in basis[0]]+[dx-factor*xmin],[factor*v for v in basis[1]]+[dy-factor*ymin]]
        def on_sheet(point):return [sum(row[i]*point[i] for i in range(3))+row[3] for row in matrix]
        printed=[];horizontal=vertical=0
        for dimension in dimensions:
            a,b=on_sheet(dimension['start_point']),on_sheet(dimension['end_point'])
            if math.dist(a,b)<.1:raise StudError('plan_layout',f'Dimension {dimension["id"]} is edge-on.')
            if crop and any(p[0]<dx-.1 or p[0]>dx+drawing.width+.1 or p[1]<dy-.1 or p[1]>dy+drawing.height+.1 for p in (a,b)):
                raise StudError('plan_layout',f'Dimension {dimension["id"]} is outside the cropped detail.')
            c.setStrokeColor(colors.HexColor('#486557'));c.setFillColor(colors.HexColor('#25372f'));c.setLineWidth(.4);c.setFont('Helvetica',7.5)
            label=(dimension.get('label','')+' '+format_length(dimension['value'],self.units)).strip()
            if abs(a[0]-b[0])>=abs(a[1]-b[1]):
                at=dy-14-horizontal*18;horizontal+=1
                for p in (a,b):c.line(p[0],p[1],p[0],at-3);c.line(p[0]-2,at-2,p[0]+2,at+2)
                c.line(a[0],at,b[0],at);c.drawCentredString((a[0]+b[0])/2,at+3,label)
            else:
                at=dx-12-vertical*18;vertical+=1
                for p in (a,b):c.line(p[0],p[1],at-3,p[1]);c.line(at-2,p[1]-2,at+2,p[1]+2)
                c.line(at,a[1],at,b[1]);c.saveState();c.translate(at-3,(a[1]+b[1])/2);c.rotate(90);c.drawCentredString(0,0,label);c.restoreState()
            printed.append(dict(id=dimension['id'],value=dimension['value'],start=a,end=b,label=label))
        # One callout per fabrication type avoids repeating 30 identical stud
        # labels. The cut schedule carries its exact count and member mapping.
        anchors={}
        for pid in projection.get('section_objects') if projection.get('section_objects') is not None else ids:
            anchor=on_sheet(self.model.shapes[pid]['world'].Center().toTuple())
            if crop:
                box=self.model.shapes[pid]['world'].BoundingBox()
                corners=[on_sheet((px,py,pz)) for px in (box.xmin,box.xmax) for py in (box.ymin,box.ymax) for pz in (box.zmin,box.zmax)]
                if max(p[0] for p in corners)<dx or min(p[0] for p in corners)>dx+drawing.width or max(p[1] for p in corners)<dy or min(p[1] for p in corners)>dy+drawing.height:continue
                anchor=[max(dx,min(dx+drawing.width,anchor[0])),max(dy,min(dy+drawing.height,anchor[1]))]
            anchors.setdefault(self.labels[pid],anchor)
        c.setFont('Helvetica',8)
        rows=max(1,math.floor((height-50)/11))
        for index,(label,anchor) in enumerate(sorted(anchors.items(),key=lambda pair:pair[1][1],reverse=True)):
            column,row=divmod(index,rows);ay=y+height-40-row*11
            if column>1:raise StudError('plan_layout','Too many fabrication types for this drawing panel.')
            ax=x+width-48+column*25;c.setStrokeColor(colors.HexColor('#a0aaa3'));c.setLineWidth(.3);c.line(*anchor,ax-3,ay)
            c.setFillColor(colors.HexColor('#25372f'));c.drawString(ax,ay-2,label)
        name=f'view-{digest(view["id"].encode())[:16]}.svg';atomic_write(self.directory/name,projection.pop('svg'))
        self.pages[-1]['views'].append(dict(view_id=view['id'],label=view['label'],scale_denominator=scale,objects=ids,
            world_to_sheet=matrix,dimensions=printed,projection=projection,svg=name,
            drawing_bounds_points=[dx,dy,dx+drawing.width,dy+drawing.height],panel_bounds_points=[x,y,x+width,y+height]))

    def lists(self):
        width=self.body_width
        self.new_page('Cut schedule','cuts')
        self.text('C-labels identify identical finished parts and cut recipes. Counts include every physical part. Member identities and original marks are in parts.csv. All blank dimensions use the part’s local stock frame.')
        recipes={};details=[];rows=[]
        for group in self.groups:
            blank=group['blank'];operations=blank.get('operations',[])
            special=[op for op in operations if op.get('kind') not in ('square_cut','panel_cut')]
            code='Square cut' if any(op.get('kind')=='square_cut' for op in operations) else 'Panel cut'
            if special:
                key=digest(normalized(special))
                if key not in recipes:
                    recipes[key]=f'D{len(recipes)+1:02d}';details.append((recipes[key],' '.join(operation_text(op,self.units) for op in special)))
                code=recipes[key]
            size=' × '.join(format_length(v,self.units) for v in blank.get('size',[])) or 'Unspecified'
            for operation in operations:
                if operation.get('kind')=='square_cut':
                    finished=operation.get('finished_length')
                    if finished is not None and (not blank.get('size') or abs(finished-max(blank['size']))>unit_defaults(self.model.units)['query_tolerance']):
                        size+='; finish length '+format_length(finished,self.units)
                elif operation.get('kind')=='panel_cut':
                    finished=operation.get('finished_size')
                    axes=blank.get('panel_axes',[0,1])
                    if finished and (len(blank.get('size',[]))!=3 or any(abs(finished[i]-blank['size'][axis])>unit_defaults(self.model.units)['query_tolerance'] for i,axis in enumerate(axes))):
                        size+='; finish panel '+' × '.join(format_length(v,self.units) for v in finished[:2])
            material='/'.join(self.materials[key]['label'] for key in group['material_keys']) or (group.get('material') or 'Unknown')
            rows.append([group['label']+'/'+material,len(group['objects']),group['example'],size,code])
        self.flow_table('Cut types',['Cut / stock','Qty','Typical part','Starting blank','Cut'],rows,
            [width*.10,width*.04,width*.23,width*.50,width*.13],'cuts')
        self.flow_table('Special cutting instructions',['Detail','Instructions'],details,[width*.1,width*.9],'cut_details')
        self.purchase_lists()
        self.compact_sheets()
        self.assembly_steps()
        self.review_notes()
        self.close_page()

    def material_description(self,material,product_id,spec):
        description=material+' · '+product_id.replace('.',' ')
        for key in ('material','species','grade','type'):
            if spec.get(key):description+=' · '+str(spec[key])
        if spec.get('stock_length'):description+=' · '+format_length(float(spec['stock_length']),self.units)
        if spec.get('section'):description+=' · '+' × '.join(format_length(float(v),self.units) for v in spec['section'])
        if spec.get('thickness'):description+=' · '+format_length(float(spec['thickness']),self.units)+' thick'
        if spec.get('sheet'):description+=' · '+' × '.join(format_length(float(v),self.units) for v in spec['sheet'])+' sheet'
        for key,value in spec.items():
            if key in ('material','species','grade','type','stock_length','section','thickness','sheet','length_unit'):continue
            label=key.replace('_',' ')
            if key in ('length','width','height','depth','diameter') and isinstance(value,(int,float)):
                value=format_length(value,self.units)
            elif key=='size' and isinstance(value,list):
                value=' × '.join(format_length(float(v),self.units) for v in value)
            elif isinstance(value,(dict,list)):
                value=json.dumps(value,ensure_ascii=False,sort_keys=True)
            description+=' · '+label+': '+str(value)
        return description

    def purchase_lists(self):
        width=self.body_width;estimate=self.estimate or {};currency=estimate.get('currency','')
        rows=[];defined=set()
        for row in estimate.get('rows',[]):
            material=self.demand_material.get(row.get('demand_id'),'');defined.add(material)
            description=self.material_description(material,row['product_id'],row['specification'])
            quote=row.get('quote') or {}
            price=f'{quote.get("currency",currency)} {row["unit_price"]}' if row.get('unit_price') is not None else 'Missing'
            evidence=(f'{quote.get("kind","")} · {quote.get("supplier","")} · {quote.get("quote_date","")} · {quote.get("source","")}') if quote else ''
            rows.append([description,f'{row["quantity"] or "?"} {row["purchase_unit"]}'+(f' / {row["pack_size"]} each' if float(row.get('pack_size',1))!=1 else ''),
                         price,evidence,(currency+' '+row['line_total']) if row.get('line_total') is not None else 'Missing'])
        self.flow_table('Material purchases',['Purchase','Quantity','Unit price','Saved quote','Amount'],rows,
            [width*.3,width*.16,width*.13,width*.27,width*.14],'materials')
        missing=[[item['label'],self.material_description(item['label'],item['product_id'],item['specification'])]
                 for item in self.materials.values() if item['label'] not in defined]
        self.flow_table('Material specifications — purchase estimate unavailable',['Stock','Specification'],missing,
            [width*.1,width*.9],'materials')
        self.text(f'Known subtotal {currency} {estimate.get("known_subtotal","unavailable")}; tax {estimate.get("tax","unavailable")}; contingency {estimate.get("contingency","unavailable")}. '+
                  (f'Total {currency} {estimate["total"]}.' if estimate.get('total') is not None else 'Total incomplete: missing quantities/prices are not zero.'),title='Materials',kind='materials')
        # Group repeated board allocations using physical cut types, not IDs.
        groups={}
        for row in estimate.get('rows',[]):
            for stock in row.get('stock',[]):
                if 'length' not in stock:continue
                cuts=[dict(label=self.labels.get(cut['object_id'],'Missing: '+cut['object_id']),length=cut['length'],kerf_before=cut.get('kerf_before','0')) for cut in stock['cuts']]
                key=digest(dict(spec=row['specification'],length=stock['length'],cuts=cuts,offcut=stock['remaining'],trailing=stock.get('trailing_kerf')))
                if key not in groups:groups[key]=dict(label=f'B{len(groups)+1:02d}',quantity=0,stock=stock,cuts=cuts,specification=row['specification'],material=self.demand_material.get(row.get('demand_id'),''),boards=[])
                groups[key]['quantity']+=1;groups[key]['boards'].append(stock['id'])
        self.inventory['boards']=list(groups.values())
        rows=[]
        for group in groups.values():
            stock=group['stock'];section=group['specification'].get('section',[])
            size=group['material']+' · '+' × '.join(format_length(float(v),self.units) for v in section)+' × '+format_length(float(stock['length']),self.units)
            cuts=' + '.join(cut['label']+' ('+format_length(float(cut['length']),self.units)+')' for cut in group['cuts'])
            if stock.get('kerf') is not None:cuts+='; kerf '+format_length(float(stock['kerf']),self.units)
            loss=stock.get('trailing_kerf');offcut=format_length(float(stock['remaining']),self.units)
            if loss is None:offcut+=' including final kerf'
            rows.append([group['label'],group['quantity'],size,cuts,offcut])
        self.flow_table('Board cutting plan — repeat each row for its quantity',['Plan','Qty','Stock section × length','Cuts in order; allow saw kerf','Reusable offcut'],rows,
            [width*.07,width*.06,width*.29,width*.42,width*.16],'stock_cuts')
        self.text('Cut lengths are blank lengths. Kerf between cuts and before offcuts is included in the saved allocation. Do not substitute a smaller stock section. Allowances and purchase overrides are separate from the required cut counts.',title='Board cutting plan',kind='stock_cuts')

    def compact_sheets(self):
        sheets={}
        for demand in self.manifest['demands']:
            for sheet in demand.get('sheets') or []:
                panels=[dict(label=self.labels.get(p['object_id'],'Missing: '+p['object_id']),origin=p['origin'],size=p['size']) for p in sheet['panels']]
                signature=digest(normalized(dict(specification=demand['specification'],size=sheet['size'],panels=panels,kerf=sheet.get('kerf',0))))
                if signature not in sheets:sheets[signature]=dict(label=f'S{len(sheets)+1:02d}',quantity=0,sheet=sheet,panels=panels,sheets=[],material=self.demand_material[demand['id']],specification=demand['specification'])
                sheets[signature]['quantity']+=1;sheets[signature]['sheets'].append(sheet['id'])
        self.inventory['sheets']=list(sheets.values())
        values=list(sheets.values())
        for start in range(0,len(values),9):
            self.new_page('Sheet cutting layouts','sheet_layout',layouts=[])
            self.text('Repeat each layout for its quantity. C-labels refer to the cut schedule; special cuts use the D-details. Dashed outlines are blanks, solid lines are finished edges. Preserve the specified kerf.')
            width=(self.body_width-20)/3;height=(self.current_y-self.margin-68-20)/3
            for index,group in enumerate(values[start:start+9]):
                x=self.margin+(index%3)*(width+10);top=self.current_y-(index//3)*(height+10)
                sheet=group['sheet'];sw,sh=sheet['size'];thickness=group['specification'].get('thickness')
                thickness=format_length(float(thickness),self.units) if thickness is not None else 'unspecified thickness'
                self.canvas.setFont('Helvetica-Bold',8);self.canvas.setFillColor(colors.HexColor('#25372f'))
                self.canvas.drawString(x,top-8,f'{group["label"]}/{group["material"]} · {group["quantity"]} sheet(s) · {thickness}')
                required=max(sw*self.points_per_unit/(width-12),sh*self.points_per_unit/(height-48))
                scale=next(n for n in (5,10,20,25,30,40,50,75,100,150,200) if n>=required);factor=self.points_per_unit/scale
                dx=x+(width-sw*factor)/2;bottom=top-20-sh*factor
                c=self.canvas;c.setFillColor(colors.HexColor('#f5f8f4'));c.setStrokeColor(colors.HexColor('#b0bcb2'));c.rect(dx,bottom,sw*factor,sh*factor,stroke=1,fill=1)
                for part,summary in zip(sheet['panels'],group['panels']):
                    pid=part['object_id'];px,py=part['origin'];w,h=part['size']
                    if pid not in self.model.shapes:
                        c.setFillColor(colors.HexColor('#9d492e'));c.setFont('Helvetica',7)
                        c.drawString(dx+px*factor+2,bottom+(py+h)*factor-10,'Missing part — see review')
                        continue
                    entry=self.model.shapes[pid]
                    axes=(self.model.objects[pid].get('blank') or {}).get('panel_axes',[0,1]);normal=({0,1,2}-set(axes)).pop()
                    vectors=[[1 if i==axis else 0 for i in range(3)] for axis in (axes[0],axes[1],normal)]
                    # Preserve either sheet-plane handedness by using the local
                    # projected bounds, as in the expanded native sheet views.
                    direction=cq.Vector(*vectors[0]).cross(cq.Vector(*vectors[1]));view=dict(id=pid,objects=[pid],direction=direction.toTuple(),up=vectors[1],dimensions=[])
                    local=SimpleNamespace(units=self.model.units,shapes={pid:dict(entry,world=entry['local'])},objects={pid:self.model.objects[pid]},assemblies={})
                    drawing,projection=project_vector(local,view,scale)
                    ox=dx+px*factor;oy=bottom+py*factor
                    c.saveState();c.setDash(2,2);c.setStrokeColor(colors.HexColor('#96a399'));c.rect(ox,oy,w*factor,h*factor,stroke=1,fill=0);c.restoreState()
                    renderPDF.draw(drawing,c,ox+projection['bounds']['min'][0]*factor,oy+projection['bounds']['min'][1]*factor)
                    c.setFillColor(colors.HexColor('#25372f'));c.setFont('Helvetica',7)
                    label=summary['label']
                    if c.stringWidth(label,'Helvetica',7)+4>w*factor and h*factor>=c.stringWidth(label,'Helvetica',7)+4:
                        # Put narrow-strip labels along the strip so adjacent
                        # cut types remain distinct at the actual print scale.
                        c.saveState();c.translate(ox+(w*factor+5)/2,oy+h*factor-3);c.rotate(90)
                        c.drawRightString(0,0,label);c.restoreState()
                    else:c.drawString(ox+2,oy+h*factor-9,label)
                c.setFont('Helvetica',7);c.drawString(x,bottom-12,f'{format_length(sw,self.units)} × {format_length(sh,self.units)} · 1:{scale}')
                c.drawString(x,bottom-22,'Kerf '+format_length(sheet.get('kerf',0),self.units))
                self.pages[-1]['layouts'].append(dict(label=group['label'],quantity=group['quantity'],scale_denominator=scale,
                    bounds_points=[dx,bottom,dx+sw*factor,bottom+sh*factor],sheet_ids=group['sheets']))
        self.close_page()

    def assembly_steps(self):
        connections={connection['id']:connection for connection in self.manifest['connections']}
        remaining=ordered_steps(self.manifest['steps']);groups=[];mapped={}
        while remaining:
            ready=[step for step in remaining if all(key in mapped for key in step['prerequisites'])]
            if not ready:ready=[remaining[0]]
            first=ready[0]
            def signature(step):return digest(dict(text=step['text'],prerequisites=sorted({mapped.get(key,key) for key in step['prerequisites']}),
                connections=[connections[key]['description'] for key in step['connections'] if key in connections]))
            group=[step for step in ready if signature(step)==signature(first)]
            number=len(groups)+1
            for step in group:mapped[step['id']]=number;remaining.remove(step)
            groups.append(group)
        self.new_page('Assembly sequence','steps')
        for number,group in enumerate(groups,1):
            parts=[part for step in group for part in step['parts']];labels=sorted({self.labels[p] for p in parts if p in self.labels})
            prerequisites=sorted({mapped[key] for step in group for key in step['prerequisites'] if key in mapped and mapped[key]!=number})
            views=sorted({self.view_sheets[step['view']] for step in group if step.get('view') in self.view_sheets})
            self.text(f'{number}. '+group[0]['text']+(f' Repeat for {len(group)} assemblies.' if len(group)>1 else ''),title='Assembly sequence',kind='steps',bold=True)
            self.text('Cut types '+', '.join(labels)+'. '+('After step '+', '.join(map(str,prerequisites))+'. ' if prerequisites else '')+
                      ('Drawings on sheet '+', '.join(map(str,views))+'.' if views else ''),title='Assembly sequence',kind='steps')
            selected={key:connections[key] for step in group for key in step['connections'] if key in connections}
            for description in dict.fromkeys(connection['description'] for connection in selected.values()):self.text(description,title='Assembly sequence',kind='steps')
            hardware=defaultdict(int)
            for connection in selected.values():
                if connection.get('hardware'):hardware[connection['hardware']['product_id']]+=connection['hardware']['count']
            if hardware:self.text('Hardware: '+ '; '.join(f'{count} × {product}' for product,count in hardware.items())+'.',title='Assembly sequence',kind='steps')
            self.exploded_group([step for step in group if step.get('exploded')])
            self.inventory['steps'].append(dict(number=number,step_ids=[step['id'] for step in group],parts=parts,prerequisites=prerequisites,cut_labels=labels,hardware=dict(hardware)))
            self.current_y-=5

    def exploded_group(self,steps):
        for start in range(0,len(steps),2):
            pair=steps[start:start+2]
            if self.current_y-155<self.margin+60:self.new_page('Assembly sequence — illustrations','steps')
            top=self.current_y;cell=(self.body_width-16*(len(pair)-1))/len(pair)
            for index,step in enumerate(pair):self.exploded(step,self.margin+index*(cell+16),top,cell)
            self.current_y=top-155

    def exploded(self,step,x,top,width):
        from .cad import shape_bounds
        parts=[p for p in step['parts'] if p in self.model.objects]
        shapes={};objects={}
        for pid in parts:
            shape=self.model.shapes[pid]['world'].moved(cq.Location(cq.Vector(*step.get('exploded',{}).get(pid,[0,0,0]))))
            shapes[pid]=dict(self.model.shapes[pid],world=shape)
            objects[pid]=dict(self.model.objects[pid],bounds=shape_bounds(shape))
        model=SimpleNamespace(units=self.model.units,shapes=shapes,objects=objects,assemblies={})
        view=dict(id=step['id']+'.exploded',objects=parts,direction=[1,-1,1],up=[0,0,1],dimensions=[])
        # Project once at unit scale to choose a physical illustration scale.
        drawing,projection=project_vector(model,view,1)
        required=max(drawing.width/width,drawing.height/120)
        scale=next((n for n in (1,2,5,10,20,25,40,50,75,100,200,500,1000) if n>=required),None)
        if scale is None:raise StudError('plan_layout','The exploded illustration does not fit.')
        drawing,projection=project_vector(model,view,scale)
        caption=Paragraph(escape('Exploded: '+step['id']),self.cell_style);_,ch=caption.wrap(width,30)
        if ch>30:raise StudError('plan_layout','The assembly illustration label needs a shorter step ID.')
        caption.drawOn(self.canvas,x,top-ch)
        x=x+(width-drawing.width)/2;y=top-30-drawing.height
        renderPDF.draw(drawing,self.canvas,x,y)
        name='step-'+digest(step['id'].encode())[:16]+'.svg';atomic_write(self.directory/name,projection.pop('svg'))
        self.pages[-1].setdefault('illustrations',[]).append(dict(step_id=step['id'],objects=parts,exploded=step['exploded'],svg=name,
            bounds_points=[x,y,x+drawing.width,y+drawing.height],scale_denominator=scale))

    def review_notes(self):
        findings=self.review['findings'][:]
        if (self.estimate or {}).get('status')!='complete':findings.append(dict(category='estimate',message='Prices or quantities are incomplete; missing values are not zero.',target=None))
        for finding in findings:self.text(f'Review — {finding["message"]}'+(f' ({finding["target"]})' if finding.get('target') else ''),title='Packet review',kind='review')
        for note in self.manifest.get('notes',[]):self.text(note,title='Project notes',kind='review')
        self.text('Saved estimate '+(self.estimate or {}).get('id','unavailable')+'. Price basis '+(self.estimate or {}).get('price_basis_id','unavailable')+'.',title='Packet records',kind='review')
        index=[]
        for page in self.pages:
            title='; '.join(view['label'] for view in page.get('views',[])) or page['title']
            index.append([page['number'],title])
        self.flow_table('Sheet index',['Sheet','Contents'],index,[self.body_width*.08,self.body_width*.92],'index')
