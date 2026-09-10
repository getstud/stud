"""Vector construction/review packets from a fixed evaluated model.

Projection is performed by OCCT. Dimensions are measured before projection;
the PDF's explicit millimeter-to-point transform is archived for verification.
"""
import csv
from html import escape
import io
import math
from pathlib import Path
import re
import time
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import cadquery as cq
from cadquery.occ_impl.exporters.svg import getSVG
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg

from .checks import resolve_point
from .contracts import StudError, atomic_write, digest, read_json, write_json
from .evaluated import load_model, object_scope, location_from_matrix
from .fabrication import audit_fabrication

POINTS_PER_MM = 72 / 25.4
GENERATOR_VERSION = 4
PAPER = {'letter':letter, 'a4':A4}


def format_length(mm, units='imperial'):
    if units == 'mm':
        return f'{mm:g} mm'
    from fractions import Fraction
    value = Fraction(round(mm / 25.4 * 16),16)
    whole, remainder = divmod(value.numerator, value.denominator)
    text = str(whole) if whole or not remainder else ''
    if remainder:
        text += (' ' if text else '') + f'{remainder}/{value.denominator}'
    return f'{mm:.2f} mm (~{text} in)' if abs(float(value)*25.4-mm)>1e-6 else text+' in'


def operation_text(operation, units='imperial'):
    kind=operation.get('kind')
    if kind=='square_cut':
        length=operation.get('finished_length_mm')
        return 'Square-cut both ends'+(f' to {format_length(length,units)}.' if length else '.')
    if kind=='panel_cut':
        size=operation.get('finished_size_mm',[])
        return 'Cut panel'+(' to '+' x '.join(format_length(v,units) for v in size[:2]) if size else '')+'.'
    if kind=='bore':
        text=f'Bore {format_length(operation["diameter_mm"],units)} diameter'+(' through.' if operation.get('through') else '.')
        if operation.get('center_mm'):text+=' Center '+', '.join(format_length(v,units) for v in operation['center_mm'])+' from the local blank corner.'
        if operation.get('axis'):text+=f' Drill through the local {operation["axis"]} direction.'
        return text
    if kind=='slope_cut':return f'Slope cut: rise/run {operation["slope"]:g}.'
    if kind=='plumb_cut':return f'Cut both ends plumb at rise/run {operation["slope"]:g}; horizontal run {format_length(operation["horizontal_run_mm"],units)}. The listed blank length includes the angled end cuts.'
    if kind=='birdsmouth':
        points=operation.get('stock_seat_endpoints_mm')
        if points:return 'Mark the seat line on the rectangular blank Y-Z face between '+ ' and '.join(f'(Y {format_length(p[1],units)}, Z {format_length(p[2],units)})' for p in points)+'. Cut the seat between these marks; its assembled horizontal width is '+format_length(operation['seat_mm'],units)+'.'
        return f'Birdsmouth seat {format_length(operation["seat_mm"],units)} wide, at {format_length(operation["seat_z_mm"],units)} above the {operation.get("frame","unspecified")} datum.'
    if kind=='beveled_edge':return 'Bevel the top edge from '+format_length(operation['low_height_mm'],units)+' to '+format_length(operation['high_height_mm'],units)+f' high, rise/run {operation["slope"]:g}.'
    if kind=='beveled_end':return 'Cut the upper end to '+format_length(operation['low_length_mm'],units)+' on one edge and '+format_length(operation['high_length_mm'],units)+' on the other.'
    if kind=='rectangular_opening':return 'Cut '+operation.get('opening_id','opening')+' rectangle '+ ' x '.join(format_length(v,units) for v in operation['size_mm'])+'; lower-left offset '+', '.join(format_length(v,units) for v in operation['origin_mm'])+' on the sheet.'
    if kind=='housing':return (operation.get('description') or 'Cut housing.')+' Size '+ ' x '.join(format_length(v,units) for v in operation['size_mm'])+'; local origin '+', '.join(format_length(v,units) for v in operation['origin_mm'])+'.'
    if kind=='profile_cut':return (operation.get('description') or 'Cut the closed outline on the local blank face.')+(' Join coordinates '+ '; '.join('('+', '.join(format_length(v,units) for v in point)+')' for point in operation['profile_mm'])+'.' if operation.get('profile_mm') else ' Outline coordinates are missing.')
    return operation.get('description') or 'Unspecified operation; review required.'


def preflight(model, manifest):
    findings=audit_fabrication(manifest)
    def missing(category, target, message):
        findings.append(dict(category=category, target=target, message=message))
    if manifest['completion']['geometry'] != 'complete':
        missing('partial_geometry',None,'Only a diagnostic packet can be generated from partial geometry.')
    checks=manifest.get('checks',{})
    if not checks.get('all_passed'):
        missing('geometric_review',None,'Geometric requirements are failed, unresolved, unsupported, or not fully covered.')
    for item in checks.get('findings',[]):
        if item['status'] != 'passed':
            missing('geometric_finding',item['requirement_id'],f"{item['status']}: {item.get('explanation') or item['kind']}")
    dimensions={d['id']:d for d in manifest['dimensions']}
    resolved={}
    for key,dimension in dimensions.items():
        try:
            if dimension.get('measurement','distance') not in ('distance','length'):
                raise StudError('unsupported_measurement','This packet requires an explicit supported dimension measurement.')
            a,b=resolve_point(model,dimension['start']),resolve_point(model,dimension['end'])
            value=math.dist(a,b)
            if 'expected_mm' in dimension and abs(value-dimension['expected_mm'])>dimension.get('tolerance_mm',.01):
                missing('stale_dimension',key,'The authored dimension expectation no longer matches geometry.')
            resolved[key]=dict(**dimension,start_point=a,end_point=b,value_mm=value)
        except (StudError,ValueError,TypeError) as error:
            missing('unresolved_dimension',key,str(error))
    for view in manifest['drawings']:
        try:
            object_scope(model,view.get('objects'))
        except StudError as error:
            missing('unresolved_view',view['id'],str(error))
        for ref in view['dimensions']:
            if ref not in resolved:
                missing('unresolved_dimension',view['id'],f'Dimension {ref} is unavailable.')
        if view.get('detail_of') and view['detail_of'] not in {drawing['id'] for drawing in manifest['drawings']}:
            missing('unresolved_detail',view['id'],'The parent drawing for this detail is missing.')
    for obj in model.objects.values():
        blank=obj.get('blank')
        if not blank or not blank.get('size_mm') or not blank.get('operations'):
            missing('missing_cut_information',obj['id'],'A reproducible cut needs a specified blank and operations.')
    connections={c['id']:c for c in manifest['connections']}
    for connection in connections.values():
        for issue in connection.get('unresolved', []):
            missing('incomplete_connection',connection['id'],issue)
        if not connection.get('description'):
            missing('missing_connection_detail',connection['id'],'Connection instructions are missing.')
        for part in connection['parts']:
            if part not in model.objects:
                missing('unresolved_connection',connection['id'],f'Part {part} is missing.')
    steps={s['id']:s for s in manifest['steps']}
    if not steps:
        missing('missing_steps',None,'No assembly instructions were authored.')
    view_ids={v['id'] for v in manifest['drawings']}
    for step in steps.values():
        if not step.get('text','').strip():missing('missing_step_text',step['id'],'Assembly instructions are missing.')
        for part in step['parts']:
            if part not in model.objects:
                missing('unresolved_step',step['id'],f'Part {part} is missing.')
        for connection in step['connections']:
            if connection not in connections:
                missing('unresolved_step',step['id'],f'Connection {connection} is missing.')
        for prerequisite in step['prerequisites']:
            if prerequisite not in steps:
                missing('unresolved_step',step['id'],f'Prerequisite {prerequisite} is missing.')
        if step.get('view') and step['view'] not in view_ids:
            missing('unresolved_step',step['id'],f'View {step["view"]} is missing.')
        for part,offset in step.get('exploded',{}).items():
            if part not in step['parts'] or not isinstance(offset,(tuple,list)) or len(offset)!=3 or not all(isinstance(value,(int,float)) and math.isfinite(value) for value in offset):
                missing('unresolved_exploded_part',step['id'],f'Exploded part {part} needs a valid referenced part and finite displacement.')
    in_steps={part for step in steps.values() for part in step['parts']}
    for part in set(model.objects)-in_steps:
        missing('missing_part_step',part,'No assembly step references this physical part.')
    visiting,done=set(),set()
    def visit(key):
        if key in visiting:
            missing('cyclic_steps',key,'Assembly prerequisites contain a cycle.')
            return
        if key in done or key not in steps:
            return
        visiting.add(key)
        for dependency in steps[key]['prerequisites']:
            visit(dependency)
        visiting.remove(key);done.add(key)
    for key in steps:
        visit(key)
    demands=manifest['demands']
    if not demands:
        missing('missing_materials',None,'No material demands were authored.')
    for demand in demands:
        for problem in demand.get('unresolved',[]):
            missing('incomplete_material',demand['id'],problem)
        for sheet in demand.get('sheets') or []:
            panels=sheet.get('panels',[])
            if not panels:
                missing('incomplete_sheet',sheet['id'],'Sheet has no identified panel cuts.')
            for index,panel in enumerate(panels):
                x,y=panel['origin_mm'];w,h=panel['size_mm']
                sw,sh=sheet['size_mm'];kerf=sheet.get('kerf_mm',0)
                if x<0 or y<0 or w<=0 or h<=0 or x+w>sw+.01 or y+h>sh+.01:
                    missing('sheet_fit',sheet['id'],f'Panel {panel["object_id"]} does not fit its actual sheet.')
                if panel['object_id'] not in model.objects or not panel.get('supported_edges'):
                    missing('incomplete_sheet',sheet['id'],'Panel targets and supported edges must be explicit.')
                elif panel['object_id'] in model.objects:
                    blank=model.objects[panel['object_id']].get('blank') or {}
                    axes=blank.get('panel_axes',[0,1]);size=blank.get('size_mm',[])
                    if len(size)!=3 or len(axes)!=2 or any(axis not in (0,1,2) for axis in axes) or any(abs(size[axis]-measure)>.01 for axis,measure in zip(axes,(w,h))):
                        missing('stale_sheet_cut',panel['object_id'],'The sheet cut dimensions differ from the part blank.')
                    for edge,supports in panel.get('supported_edges',{}).items():
                        if isinstance(supports,str):supports=[supports]
                        if not isinstance(supports,list) or not supports or any(part not in model.objects for part in supports):
                            missing('unresolved_sheet_support',panel['object_id'],f'Support references for {edge} are missing.')
                    if panel.get('edge_requirement'):
                        requirement=next((r for r in manifest['requirements'] if r['id']==panel['edge_requirement']),None)
                        if not requirement or requirement['kind']!='panel_edge_support' or requirement['targets'][0]!=panel['object_id']:
                            missing('unresolved_sheet_support',panel['object_id'],'The named native edge-backing requirement is missing or references another panel.')
                for other in panels[:index]:
                    ox,oy=other['origin_mm'];ow,oh=other['size_mm']
                    if x<ox+ow+kerf-.01 and ox<x+w+kerf-.01 and y<oy+oh+kerf-.01 and oy<y+h+kerf-.01:
                        missing('sheet_overlap',sheet['id'],'Panel cuts overlap or omit the declared cutting loss.')
    return dict(status='complete' if not findings else 'review', findings=findings,
                dimensions=resolved, geometry=manifest['completion']['geometry'],
                checks=manifest['completion']['checks'], quantities=manifest['completion']['quantities'])


def view_basis(view):
    direction=cq.Vector(*view['direction']).normalized()
    up=cq.Vector(*view.get('up',[0,0,1]))
    if abs(up.normalized().dot(direction)) > .999:
        raise StudError('invalid_view','The view up vector cannot be parallel to its direction.')
    right=up.cross(direction).normalized()
    vertical=direction.cross(right).normalized()
    return right,vertical,direction


def crop_bounds(view):
    """An optional rectangle in the drawing's right/up plane, in millimeters."""
    crop=view.get('crop_mm')
    if crop is None:return None
    if (not isinstance(crop,(list,tuple)) or len(crop)!=4 or
        not all(isinstance(v,(int,float)) and math.isfinite(v) for v in crop) or
        crop[2]<=crop[0] or crop[3]<=crop[1]):
        raise StudError('invalid_view','crop_mm requires [left, bottom, right, top] in the view plane.')
    return list(crop)


def project_vector(model, view, scale):
    ids=object_scope(model,view.get('objects'))
    if not ids:
        raise StudError('unresolved_view','A drawing has no available objects.')
    shape=cq.Compound.makeCompound([model.shapes[key]['world'] for key in ids])
    section_objects=None
    if view.get('section'):
        section=view['section']
        algorithm=BRepAlgoAPI_Section(shape.wrapped,gp_Pln(gp_Pnt(*section['origin']),gp_Dir(*section['normal'])),False)
        algorithm.ComputePCurveOn1(True);algorithm.Approximation(True);algorithm.Build()
        if not algorithm.IsDone() or algorithm.Shape().IsNull():
            raise StudError('unresolved_section','The requested cut plane produced no section.')
        shape=cq.Shape.cast(algorithm.Shape())
        if not shape.Edges():
            raise StudError('unresolved_section','The requested section contains no edges.')
        section_objects=[]
        for key in ids:
            cut=BRepAlgoAPI_Section(model.shapes[key]['world'].wrapped,gp_Pln(gp_Pnt(*section['origin']),gp_Dir(*section['normal'])),True)
            if cut.IsDone() and not cut.Shape().IsNull() and cq.Shape.cast(cut.Shape()).Edges():section_objects.append(key)
    right,vertical,direction=view_basis(view)
    matrix=[list(vector.toTuple())+[0] for vector in (right,vertical,direction)]+[[0,0,0,1]]
    projected=shape.moved(location_from_matrix(matrix))
    bounds=projected.BoundingBox()
    if min(bounds.xlen,bounds.ylen) <= 1e-7:
        raise StudError('invalid_view','Projection is edge-on; choose a view with visible area.')
    factor=POINTS_PER_MM/scale
    left,bottom,crop_right,top=crop_bounds(view) or [bounds.xmin,bounds.ymin,bounds.xmax,bounds.ymax]
    if crop_right<bounds.xmin or left>bounds.xmax or top<bounds.ymin or bottom>bounds.ymax:
        raise StudError('unresolved_view','The cropped detail is outside its selected geometry.')
    svg=getSVG(projected,dict(projectionDir=(0,0,1),showAxes=False,showHidden=view.get('hidden_lines',True),
                              width=bounds.xlen*factor,height=None,marginLeft=0,marginTop=0,
                              strokeWidth=.45/factor,strokeColor=(45,48,46),hiddenColor=(150,155,151)))
    root=ET.fromstring(svg)
    root.set('width',str((crop_right-left)*factor));root.set('height',str((top-bottom)*factor))
    group=next(node for node in root if node.tag.endswith('g') and 'transform' in node.attrib)
    group.set('transform',f'scale({factor}, {-factor}) translate({-left},{-top})')
    if view.get('crop_mm'):
        ns='{http://www.w3.org/2000/svg}'
        definitions=ET.SubElement(root,ns+'defs');clip=ET.SubElement(definitions,ns+'clipPath',{'id':'detail-crop','clipPathUnits':'userSpaceOnUse'})
        ET.SubElement(clip,ns+'rect',dict(x='0',y='0',width=str((crop_right-left)*factor),height=str((top-bottom)*factor)))
        root.remove(definitions);root.insert(0,definitions)
        # Clip in page coordinates outside the CAD transform. Clipping inside
        # a negatively scaled group is misinterpreted by some SVG converters.
        wrapper=ET.Element(ns+'g',{'clip-path':'url(#detail-crop)'})
        root.remove(group);wrapper.append(group);root.append(wrapper)
    svg_bytes=ET.tostring(root)
    drawing=svg2rlg(io.BytesIO(svg_bytes))
    if drawing is None:
        raise StudError('projection_failed','Could not convert the projected vector linework.')
    return drawing, dict(bounds=dict(min=[left,bottom],max=[crop_right,top]),crop_mm=view.get('crop_mm'),
                         factor=factor,basis=[list(v.toTuple()) for v in (right,vertical,direction)],
                         objects=ids,section_objects=section_objects,svg=svg_bytes)


class Packet:
    def __init__(self, model, manifest, directory, checkpoint, spec, review, estimate):
        self.model,self.manifest,self.directory=model,manifest,Path(directory)
        self.checkpoint,self.spec,self.review,self.estimate=checkpoint,spec,review,estimate
        self.width,self.height=PAPER[spec.get('paper','letter')]
        self.margin=float(spec.get('margin_mm',12.7))*POINTS_PER_MM
        if not 8*POINTS_PER_MM <= self.margin < min(self.width,self.height)/4:
            raise StudError('invalid_print_spec','Choose printable margins of at least 8 mm.')
        self.units=spec.get('units','imperial')
        self.canvas=Canvas(str(self.directory/'plans.pdf'),pagesize=(self.width,self.height),pageCompression=1,invariant=1)
        self.canvas.setTitle(f'{manifest["name"]} - {checkpoint[:12]}')
        self.canvas.setAuthor('stud')
        self.pages=[]
        self.text_style=ParagraphStyle('body',fontName='Helvetica',fontSize=9,leading=12,spaceAfter=6)
        self.cell_style=ParagraphStyle('cell',fontName='Helvetica',fontSize=8,leading=10,splitLongWords=True)

    def header(self,title,kind,**details):
        self.pages.append(dict(number=len(self.pages)+1,title=title,kind=kind,**details))
        canvas=self.canvas
        font_size=17
        while font_size>10 and canvas.stringWidth(title,'Helvetica-Bold',font_size)>self.width-2*self.margin:font_size-=1
        shown=title
        while canvas.stringWidth(shown,'Helvetica-Bold',font_size)>self.width-2*self.margin:shown=shown[:-4]+'...'
        canvas.setFillColor(colors.HexColor('#25372f'));canvas.setFont('Helvetica-Bold',font_size)
        canvas.drawString(self.margin,self.height-self.margin-15,shown)
        bookmark=f'sheet-{len(self.pages)}';canvas.bookmarkPage(bookmark);canvas.addOutlineEntry(title,bookmark,level=0,closed=False)
        canvas.setFillColor(colors.HexColor('#4d5752'));canvas.setFont('Helvetica',8)
        canvas.drawString(self.margin,self.height-self.margin-31,
                          f'{self.manifest["name"]} | Design {self.checkpoint[:12]} | Build {self.manifest["build_id"][-8:]}')
        if self.review['status']!='complete':
            canvas.setFillColor(colors.HexColor('#9d492e'));canvas.setFont('Helvetica-Bold',8)
            canvas.drawRightString(self.width-self.margin,self.height-self.margin-46,
                                  'DIAGNOSTIC - PARTIAL GEOMETRY' if self.review['geometry']!='complete' else 'REVIEW PACKET - SEE FINDINGS')
        canvas.setStrokeColor(colors.HexColor('#a6b0a9'));canvas.setLineWidth(.5)
        canvas.line(self.margin,self.height-self.margin-52,self.width-self.margin,self.height-self.margin-52)

    def footer(self):
        c=self.canvas;m=self.margin
        c.setStrokeColor(colors.black);c.setLineWidth(.6)
        y=m+16;length=100*POINTS_PER_MM
        c.line(m,y,m+length,y)
        for x in (m,m+length):c.line(x,y-3,x,y+3)
        c.setFillColor(colors.HexColor('#4d5752'));c.setFont('Helvetica',7)
        c.drawString(m,y+6,'Scale check: this line is exactly 100 mm (3.937 in) on the page.')
        c.drawString(m,m,'Print at 100% / Actual size. Do not fit to page.')
        c.drawRightString(self.width-m,m,f'Sheet {len(self.pages)}')
        c.showPage()

    def paragraph(self,text,x,y,width,style=None):
        paragraph=Paragraph(escape(str(text)),style or self.text_style)
        _,height=paragraph.wrap(width,self.height)
        if y-height < self.margin+54:
            raise StudError('plan_layout','Text exceeds the printable page; reduce the content per sheet.')
        paragraph.drawOn(self.canvas,x,y-height)
        return y-height-8

    def drawing(self,view):
        m=self.margin
        vertical_count=0
        right,up,_=view_basis(view)
        for key in view['dimensions']:
            dimension=self.review['dimensions'].get(key)
            if dimension:
                delta=cq.Vector(*dimension['end_point'])-cq.Vector(*dimension['start_point'])
                vertical_count+=abs(delta.dot(up))>abs(delta.dot(right))
        left_gutter=24*vertical_count
        available_w=self.width-2*m-132-left_gutter
        available_h=self.height-2*m-230
        right,up,_=view_basis(view)
        ids=object_scope(self.model,view.get('objects'))
        points=[]
        for pid in ids:
            box=self.model.shapes[pid]['world'].BoundingBox()
            points.extend((cq.Vector(x,y,z).dot(right),cq.Vector(x,y,z).dot(up))
                          for x in (box.xmin,box.xmax) for y in (box.ymin,box.ymax) for z in (box.zmin,box.zmax))
        crop=crop_bounds(view)
        projected_width=crop[2]-crop[0] if crop else max(p[0] for p in points)-min(p[0] for p in points)
        projected_height=crop[3]-crop[1] if crop else max(p[1] for p in points)-min(p[1] for p in points)
        needed=max(projected_width*POINTS_PER_MM/available_w,projected_height*POINTS_PER_MM/available_h)
        scale=view.get('scale',self.spec.get('scale'))
        if scale is None:
            scale=next((n for n in (1,2,5,10,20,25,50,100,200,500,1000) if n>=needed),None)
        if scale is None or not math.isfinite(float(scale)) or float(scale)<=0 or float(scale)+1e-9<needed:
            raise StudError('plan_layout','The requested scale does not fit the printable drawing area.')
        scale=float(scale)
        drawing,projection=project_vector(self.model,view,scale)
        x=m+16+left_gutter+(available_w-drawing.width)/2
        y=m+130+(available_h-drawing.height)/2
        self.header(view['label'],'drawing',view_id=view['id'],scale_denominator=scale,
                    units=self.units,objects=ids)
        self.canvas.setFont('Helvetica-Bold',9);self.canvas.setFillColor(colors.HexColor('#25372f'))
        self.canvas.drawString(m,self.height-m-68,f'Scale 1:{scale:g}  |  Dimensions: {self.units}')
        if view.get('detail_of'):
            parent=self.view_sheets.get(view['detail_of'],'not included')
            self.canvas.drawRightString(self.width-m,self.height-m-68,'Detail of sheet '+str(parent))
        self.canvas.saveState()
        if crop:
            boundary=self.canvas.beginPath();boundary.rect(x,y,drawing.width,drawing.height)
            self.canvas.clipPath(boundary,stroke=0,fill=0)
        renderPDF.draw(drawing,self.canvas,x,y)
        self.canvas.restoreState()
        svg_name=f'view-{digest(view["id"].encode())[:16]}.svg'
        atomic_write(self.directory/svg_name,projection.pop('svg'))
        xmin,ymin=projection['bounds']['min'];factor=projection['factor']
        right,up,_=projection['basis']
        matrix=[[factor*v for v in right]+[x-factor*xmin],
                [factor*v for v in up]+[y-factor*ymin]]
        def on_sheet(point):
            return [sum(row[i]*point[i] for i in range(3))+row[3] for row in matrix]
        children=[child for child in self.manifest['drawings'] if child.get('detail_of')==view['id'] and child['id'] in self.view_sheets]
        if children:
            self.paragraph('Details: '+ '; '.join(child['label']+' (sheet '+str(self.view_sheets[child['id']])+')' for child in children),m,self.height-m-82,self.width-2*m)
        if crop:
            self.canvas.saveState();self.canvas.setDash(3,3);self.canvas.setStrokeColor(colors.HexColor('#87968b'))
            self.canvas.rect(x,y,drawing.width,drawing.height,stroke=1,fill=0);self.canvas.restoreState()
        printed=[]
        horizontal=vertical=0
        for key in view['dimensions']:
            dimension=self.review['dimensions'].get(key)
            if not dimension:continue
            a,b=on_sheet(dimension['start_point']),on_sheet(dimension['end_point'])
            if crop and any(p[0]<x-.1 or p[0]>x+drawing.width+.1 or p[1]<y-.1 or p[1]>y+drawing.height+.1 for p in (a,b)):
                raise StudError('plan_layout',f'Dimension {key} extends outside its cropped detail.')
            if math.dist(a,b)<.1:
                raise StudError('plan_layout',f'Dimension {key} is edge-on in this drawing.')
            c=self.canvas;c.setStrokeColor(colors.HexColor('#486557'));c.setFillColor(colors.HexColor('#25372f'));c.setLineWidth(.45)
            label=(dimension.get('label')+' ' if dimension.get('label') else '')+format_length(dimension['value_mm'],self.units)
            c.setFont('Helvetica',8)
            if abs(a[0]-b[0])>=abs(a[1]-b[1]):
                line_y=y-22-horizontal*20;horizontal+=1
                if line_y<self.margin+65:raise StudError('plan_layout','Dimension lines exceed the reserved annotation area.')
                for point in (a,b):c.line(point[0],point[1]-2,point[0],line_y-4)
                c.line(a[0],line_y,b[0],line_y)
                for point in (a,b):c.line(point[0]-3,line_y-3,point[0]+3,line_y+3)
                c.drawCentredString((a[0]+b[0])/2,line_y+5,label)
            else:
                line_x=x-20-vertical*20;vertical+=1
                if line_x<self.margin:raise StudError('plan_layout','Vertical dimensions exceed the printable margin.')
                for point in (a,b):c.line(point[0]-2,point[1],line_x-4,point[1])
                c.line(line_x,a[1],line_x,b[1])
                for point in (a,b):c.line(line_x-3,point[1]-3,line_x+3,point[1]+3)
                c.saveState();c.translate(line_x-5,(a[1]+b[1])/2);c.rotate(90);c.drawCentredString(0,0,label);c.restoreState()
            printed.append(dict(id=key,value_mm=dimension['value_mm'],start=a,end=b,label=label))
        # Label callouts occupy a dedicated gutter, with ordered, nonoverlapping rows.
        callouts=[]
        for pid in projection.get('section_objects') if projection.get('section_objects') is not None else ids:
            center=self.model.shapes[pid]['world'].Center().toTuple()
            anchor=on_sheet(center)
            if crop:
                box=self.model.shapes[pid]['world'].BoundingBox()
                projected=[on_sheet((px,py,pz)) for px in (box.xmin,box.xmax) for py in (box.ymin,box.ymax) for pz in (box.zmin,box.zmax)]
                lo_x=max(x,min(p[0] for p in projected));hi_x=min(x+drawing.width,max(p[0] for p in projected))
                lo_y=max(y,min(p[1] for p in projected));hi_y=min(y+drawing.height,max(p[1] for p in projected))
                if lo_x>hi_x or lo_y>hi_y:continue
                anchor=[max(lo_x,min(hi_x,anchor[0])),max(lo_y,min(hi_y,anchor[1]))]
            callouts.append((pid,anchor))
        if len(callouts)>math.floor(available_h/13):
            # Dense building drawings use a separate part-index sheet. Do not
            # print overlapping illegible callouts to pretend they fit.
            self.paragraph('Part marks are listed in the companion part index; use detailed assembly views for dense areas.',m,m+105,self.width-2*m)
        else:
            label_x=self.width-m-75
            label_y=m+130+available_h
            for index,(pid,anchor) in enumerate(sorted(callouts,key=lambda item:item[1][1],reverse=True)):
                label_y=max(m+130+(len(callouts)-index-1)*13,min(label_y,anchor[1]+4))
                self.canvas.setStrokeColor(colors.HexColor('#a0aaa3'));self.canvas.setLineWidth(.3)
                self.canvas.line(anchor[0],anchor[1],label_x-4,label_y)
                self.canvas.setFillColor(colors.HexColor('#25372f'));self.canvas.setFont('Helvetica',8)
                self.canvas.drawString(label_x,label_y-2,self.model.objects[pid]['mark'])
                label_y-=13
        self.pages[-1].update(world_to_sheet=matrix,dimensions=printed,projection=projection,
                              drawing_bounds_points=[x,y,x+drawing.width,y+drawing.height],svg=svg_name)
        self.footer()

    def illustration(self,step,y):
        ids=[part for part in step['parts'] if part in self.model.objects]
        if not ids:return
        height=y-self.margin-86
        if height<100:
            self.footer();self.header('Assembly illustration: '+step['id'],'step_illustration',step_id=step['id'])
            y=self.height-self.margin-76;height=y-self.margin-86
        source=next((v for v in self.manifest['drawings'] if v['id']==step.get('view')),None)
        view=dict(id=step['id'],objects=ids,direction=source['direction'] if source else [1,-1,1],
                  up=source.get('up',[0,0,1]) if source else [0,0,1],hidden_lines=False)
        if step.get('exploded'):view.update(direction=[1,-1,1],up=[0,0,1])
        shapes={key:dict(value) for key,value in self.model.shapes.items()}
        for key,offset in step.get('exploded',{}).items():
            if key in shapes:shapes[key]['world']=shapes[key]['world'].moved(cq.Location(cq.Vector(*offset)))
        temporary=SimpleNamespace(shapes=shapes,objects=self.model.objects,assemblies=self.model.assemblies)
        right,up,_=view_basis(view);points=[]
        for key in ids:
            box=shapes[key]['world'].BoundingBox()
            points.extend((cq.Vector(x,y,z).dot(right),cq.Vector(x,y,z).dot(up)) for x in (box.xmin,box.xmax)
                          for y in (box.ymin,box.ymax) for z in (box.zmin,box.zmax))
        width=self.width-2*self.margin-24
        needed=max((max(p[0] for p in points)-min(p[0] for p in points))*POINTS_PER_MM/width,
                   (max(p[1] for p in points)-min(p[1] for p in points))*POINTS_PER_MM/height)
        scale=next((n for n in (1,2,5,10,20,25,50,100,200,500,1000) if n>=needed),1000)
        drawing,projection=project_vector(temporary,view,scale)
        x=self.margin+12+(width-drawing.width)/2;bottom=y-drawing.height
        renderPDF.draw(drawing,self.canvas,x,bottom)
        name=f'step-{digest(step["id"].encode())[:16]}.svg';atomic_write(self.directory/name,projection.pop('svg'))
        self.pages[-1]['illustration']=dict(svg=name,objects=ids,exploded=step.get('exploded',{}),scale_denominator=scale,
                                            bounds_points=[x,bottom,x+drawing.width,y],projection=projection)
        self.canvas.setFont('Helvetica',8);self.canvas.setFillColor(colors.HexColor('#4d5752'))
        self.canvas.drawString(self.margin,self.margin+66,'Exploded assembly illustration; use drawing dimensions.' if step.get('exploded') else f'Assembly illustration 1:{scale:g}.')

    def sheet_layouts(self):
        sheets=[sheet for demand in self.manifest['demands'] for sheet in demand.get('sheets') or []]
        for start in range(0,len(sheets),2):
            count=len(sheets[start:start+2]);width=(self.width-2*self.margin-24*(count-1))/count
            self.header('Sheet cutting layouts','sheet_layout',sheet_ids=[s['id'] for s in sheets[start:start+2]])
            layouts=[]
            for column,sheet in enumerate(sheets[start:start+2]):
                x=self.margin+column*(width+24);top=self.height-self.margin-92
                sw,sh=sheet['size_mm'];available_h=self.height-2*self.margin-290
                required=max(sw*POINTS_PER_MM/width,sh*POINTS_PER_MM/available_h)
                scale=next(n for n in (1,2,5,10,20,25,50,100,200,500,1000) if n>=required)
                factor=POINTS_PER_MM/scale;bottom=top-sh*factor
                c=self.canvas;c.setFont('Helvetica-Bold',9);c.setFillColor(colors.HexColor('#25372f'))
                c.drawString(x,top+14,f'Sheet {start+column+1} | 1:{scale}')
                c.setStrokeColor(colors.HexColor('#9aa79e'));c.setLineWidth(.6);c.setFillColor(colors.HexColor('#f6f8f5'))
                c.rect(x,bottom,sw*factor,sh*factor,fill=1,stroke=1)
                rows=[]
                for panel in sheet['panels']:
                    pid=panel['object_id']
                    if pid not in self.model.shapes:continue
                    obj=self.model.objects[pid];blank=obj.get('blank') or {};axes=blank.get('panel_axes',[0,1])
                    u=cq.Vector(*[int(i==axes[0]) for i in range(3)]);v=cq.Vector(*[int(i==axes[1]) for i in range(3)])
                    local=SimpleNamespace(objects={pid:obj},assemblies={},shapes={pid:{'world':self.model.shapes[pid]['local']}})
                    view=dict(objects=[pid],direction=u.cross(v).toTuple(),up=v.toTuple(),hidden_lines=False)
                    drawing,projection=project_vector(local,view,scale)
                    px,py=panel['origin_mm'];w,h=panel['size_mm'];bx,by=projection['bounds']['min']
                    ox=x+(px+bx)*factor;oy=bottom+(py+by)*factor
                    renderPDF.draw(drawing,c,ox,oy)
                    c.setStrokeColor(colors.HexColor('#93a699'));c.setDash(2,2);c.rect(x+px*factor,bottom+py*factor,w*factor,h*factor);c.setDash()
                    c.setFillColor(colors.HexColor('#25372f'));c.setFont('Helvetica',7)
                    c.drawString(x+px*factor+3,bottom+(py+h)*factor-10,obj['mark'])
                    rows.append(obj['mark']+': '+format_length(w,self.units)+' x '+format_length(h,self.units))
                    layouts.append(dict(sheet_id=sheet['id'],object_id=pid,mark=obj['mark'],origin_mm=[px,py],size_mm=[w,h],
                        bounds_points=[x+px*factor,bottom+py*factor,x+(px+w)*factor,bottom+(py+h)*factor],scale_denominator=scale))
                y=bottom-14
                y=self.paragraph('Blank: '+format_length(sw,self.units)+' x '+format_length(sh,self.units)+'. Kerf '+format_length(sheet.get('kerf_mm',0),self.units)+'.',x,y,width,self.cell_style)
                for row in rows:y=self.paragraph(row,x,y,width,self.cell_style)
                self.paragraph('Solid lines show actual finished outlines and openings. Dashed rectangles show starting panel blanks. See the part cuts for offsets and operations.',x,y,width,self.cell_style)
            self.pages[-1]['layouts']=layouts;self.footer()

    def table(self,title,headers,rows,widths,kind):
        remaining=[[Paragraph(escape(str(cell)),self.cell_style) for cell in headers]]+[
            [Paragraph(escape(str(cell)),self.cell_style) for cell in row] for row in rows]
        table=Table(remaining,colWidths=widths,repeatRows=1,hAlign='LEFT')
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8eee9')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
            ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
            ('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#87968b')),
            ('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#ced7d0'))]))
        tables=[table]
        while tables:
            current=tables.pop(0)
            available=self.height-2*self.margin-135
            _,height=current.wrap(self.width-2*self.margin,available)
            if height>available:
                pieces=current.split(self.width-2*self.margin,available)
                if len(pieces)<2:raise StudError('plan_layout',f'A {title} row is too tall for one page.')
                current=pieces[0];tables=pieces[1:]+tables
                _,height=current.wrap(self.width-2*self.margin,available)
            self.header(title,kind)
            current.drawOn(self.canvas,self.margin,self.height-self.margin-68-height)
            self.footer()

    def lists(self):
        width=self.width-2*self.margin
        rows=[]
        for obj in self.model.objects.values():
            blank=obj.get('blank') or {}
            size=' x '.join(format_length(v,self.units) for v in blank.get('size_mm',[])) or 'Unspecified'
            operations=' '.join(operation_text(operation,self.units) for operation in blank.get('operations',[])) or 'Unspecified'
            rows.append([obj['mark'],obj['label']+' / '+obj['id'],size,operations])
        self.table('Parts and cuts',['Mark','Part / persistent ID','Starting blank','Specified operations'],rows,
                   [width*.12,width*.29,width*.23,width*.36],'cuts')
        estimate=self.estimate or {}
        rows=[]
        for row in estimate.get('rows',[]):
            specification=row.get('specification',{});description=row['product_id'].replace('.',' ').title()
            if specification.get('stock_length_mm'):
                description+=' / '+format_length(float(specification['stock_length_mm']),self.units)+' stock'
            if specification.get('section_mm'):
                description+=' / '+ ' x '.join(format_length(float(value),self.units) for value in specification['section_mm'])+' section'
            if specification.get('thickness_mm'):
                description+=' / '+format_length(float(specification['thickness_mm']),self.units)+' thick'
            if float(row.get('pack_size',1))!=1:
                description+=' / '+str(row['pack_size'])+' per '+row['purchase_unit']
            quote=row.get('quote') or {}
            price=(f'{quote.get("currency",estimate.get("currency",""))} {row["unit_price"]} per {row["purchase_unit"]}. '
                   f'{quote.get("kind","Unspecified").title()} quote; {quote.get("supplier","Unknown supplier")}; '
                   f'{quote.get("quote_date","Undated")}. Source: {quote.get("source","Unspecified")}.') if row.get('unit_price') is not None else 'No applicable saved quote.'
            rows.append([description,row['quantity'] or 'Missing',row['purchase_unit'],row['basis']+' '+price,
                         (estimate.get('currency','')+' '+row['line_total']) if row.get('line_total') is not None else 'Missing price'])
        if rows:
            self.table('Material purchases',['Material','Quantity','Unit','Quantity and saved price basis','Amount'],rows,
                       [width*.22,width*.1,width*.12,width*.39,width*.17],'materials')
            currency=estimate.get('currency','')
            self.table('Estimate summary',['Item','Saved amount or basis'],[
                ['Known material subtotal',f'{currency} {estimate.get("known_subtotal","Unavailable")}'],
                ['Tax',f'{currency} {estimate.get("tax","Unavailable")}'],
                ['Contingency',f'{currency} {estimate.get("contingency","Unavailable")}'],
                ['Total',f'{currency} {estimate["total"]}' if estimate.get('total') is not None else 'Incomplete: missing quantities or prices are not zero.'],
                ['Estimate ID',estimate.get('id','Unavailable')],['Price basis ID',estimate.get('price_basis_id','Unavailable')]],
                [width*.28,width*.72],'estimate_summary')
        stock_rows=[]
        for row in estimate.get('rows',[]):
            for stock in row.get('stock',[]):
                if 'length_mm' not in stock:continue
                marks=[]
                for cut in stock['cuts']:
                    obj=self.model.objects.get(cut['object_id'],{})
                    marks.append(obj.get('mark','MISSING')+' '+format_length(float(cut['length_mm']),self.units))
                remainder=format_length(float(stock['remaining_mm']),self.units)
                remainder+=' reusable after final kerf' if 'trailing_kerf_mm' in stock else ' unused; saved legacy plan includes any final kerf'
                stock_rows.append([len(stock_rows)+1,format_length(float(stock['length_mm']),self.units),'; '.join(marks),remainder])
        if stock_rows:self.table('Stock cutting plan',['Board','Stock length','Cuts in order; allow kerf between cuts','Offcut / unused length'],stock_rows,
                                  [width*.08,width*.2,width*.54,width*.18],'stock_cuts')
        self.sheet_layouts()
        steps=ordered_steps(self.manifest['steps']); connections={c['id']:c for c in self.manifest['connections']}
        numbers={step['id']:index+1 for index,step in enumerate(steps)}
        drawing_sheets={page['view_id']:page['number'] for page in self.pages if page.get('view_id')}
        for index,step in enumerate(steps):
            self.header(f'Assembly {index+1}: {step["id"]}','step',step_id=step['id'])
            y=self.height-self.margin-74
            y=self.paragraph(step['text'],self.margin,y,width)
            marks=[self.model.objects[p]['mark'] if p in self.model.objects else f'MISSING {p}' for p in step['parts']]
            y=self.paragraph('Parts: '+', '.join(marks),self.margin,y,width)
            if step['prerequisites']:
                y=self.paragraph('After assembly '+', '.join(str(numbers.get(key,'MISSING '+key)) for key in step['prerequisites']),self.margin,y,width)
            if step.get('view'):
                y=self.paragraph('Drawing: sheet '+str(drawing_sheets.get(step['view'],'not included'))+' ('+step['view']+')',self.margin,y,width)
            for key in step['connections']:
                if key in connections:
                    connection=connections[key]
                    connection_marks=', '.join(self.model.objects[p]['mark'] for p in connection['parts'] if p in self.model.objects)
                    y=self.paragraph(connection['description'],self.margin,y,width)
                    if len(connection['parts'])<=12:y=self.paragraph('Connection parts: '+connection_marks,self.margin,y,width)
                    hardware=connections[key].get('hardware')
                    if hardware:y=self.paragraph(f'Hardware: {hardware["count"]} x {hardware["product_id"]}',self.margin,y,width)
            self.illustration(step,y)
            self.footer()
        findings=self.review['findings'][:]
        if estimate.get('status')!='complete':
            findings.append(dict(category='estimate',target=None,message='Estimate is incomplete or unavailable; missing prices are not zero.'))
        rows=[[f['category'],f.get('target') or '-',f['message']] for f in findings] or [['Complete','-','All declared packet references resolved. Geometric and pricing coverage are reported separately.']]
        self.table('Packet review',['Category','Reference','Finding'],rows,[width*.2,width*.25,width*.55],'review')
        if self.manifest.get('notes'):
            self.header('Project notes','notes');y=self.height-self.margin-74
            for note in self.manifest['notes']:
                _,height=Paragraph(escape(str(note)),self.text_style).wrap(width,self.height)
                if y-height<self.margin+54:
                    self.footer();self.header('Project notes - continued','notes');y=self.height-self.margin-74
                y=self.paragraph(note,self.margin,y,width)
            self.footer()
        self.table('Sheet index',['Sheet','Title','Contents'],[[page['number'],page['title'],page['kind'].replace('_',' ')] for page in self.pages],
                   [width*.1,width*.7,width*.2],'index')


def ordered_steps(steps):
    remaining=list(steps);result=[];done=set()
    while remaining:
        ready=next((step for step in remaining if set(step['prerequisites'])<=done),None)
        if ready is None:
            # Cycles and dangling prerequisites are already explicit findings.
            result.extend(remaining);break
        result.append(ready);done.add(ready['id']);remaining.remove(ready)
    return result


def generate(directory, output, *, checkpoint, print_spec=None, views=None, estimate=None, diagnostic=False, include_lists=True, expected_build=None,reproduced_from_build=None):
    started=time.perf_counter()
    model,manifest=load_model(directory,expected=expected_build)
    if manifest.get('checkpoint') and manifest['checkpoint']!=checkpoint and (expected_build or {}).get('export_checkpoint')!=checkpoint:
        raise StudError('stale_target','The plan checkpoint does not match the evaluated model.')
    review=preflight(model,manifest)
    if review['geometry']!='complete' and not diagnostic:
        raise StudError('incomplete_geometry','Only an explicitly diagnostic packet is allowed for partial geometry.')
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    spec={'paper':'letter','margin_mm':12.7,'units':'imperial','template_version':1,'layout':'compact',**(print_spec or {})}
    if spec['paper'] not in PAPER:raise StudError('invalid_print_spec','Supported papers are letter and a4.')
    if spec['units'] not in ('mm','imperial'):raise StudError('invalid_print_spec','Supported printed units are mm and imperial.')
    selected=[view for view in manifest['drawings'] if views is None or view['id'] in views]
    if not selected:raise StudError('unresolved_view','No requested drawing views are available.')
    if views and set(views)-{view['id'] for view in selected}:raise StudError('unresolved_view','A requested drawing view is missing.')
    if spec['layout'] not in ('compact','expanded'):raise StudError('invalid_print_spec','Packet layout must be compact or expanded.')
    if spec['layout']=='compact':
        from .plans_compact import CompactPacket
        packet=CompactPacket(model,manifest,output,checkpoint,spec,review,estimate)
        packet.drawings(selected)
    else:
        packet=Packet(model,manifest,output,checkpoint,spec,review,estimate)
        packet.view_sheets={view['id']:index+1 for index,view in enumerate(selected)}
        for view in selected:packet.drawing(view)
    if include_lists:packet.lists()
    packet.canvas.save()
    parts=io.StringIO();writer=csv.writer(parts)
    writer.writerow(['checkpoint','build_id','part_id','mark','label','blank_mm','operations','cut_label','material'])
    for obj in model.objects.values():writer.writerow([checkpoint,manifest['build_id'],obj['id'],obj['mark'],obj['label'],
                                                       (obj.get('blank') or {}).get('size_mm'),(obj.get('blank') or {}).get('operations'),getattr(packet,'labels',{}).get(obj['id']),obj.get('material')])
    atomic_write(output/'parts.csv',parts.getvalue().encode())
    materials=io.StringIO();writer=csv.writer(materials)
    writer.writerow(['checkpoint','build_id','estimate_id','price_basis_id','product','quantity','purchase_unit','unit_price','line_total','currency'])
    for row in (estimate or {}).get('rows',[]):writer.writerow([checkpoint,manifest['build_id'],estimate['id'],estimate['price_basis_id'],
        row['product_id'],row['quantity'],row['purchase_unit'],row['unit_price'],row['line_total'],estimate['currency']])
    atomic_write(output/'materials.csv',materials.getvalue().encode())
    result=dict(schema_version=1,project_id=manifest['project_id'],source_id=manifest['source_id'],build_id=manifest['build_id'],
        checkpoint=checkpoint,generator_version=GENERATOR_VERSION,runtime=manifest['runtime'],print_spec=spec,include_lists=include_lists,
        reproduced_from_build=reproduced_from_build,
        estimate_id=(estimate or {}).get('id'),price_basis_id=(estimate or {}).get('price_basis_id'),
        completeness={k:v for k,v in review.items() if k!='dimensions'},sheets=packet.pages,grouped_inventory=getattr(packet,'inventory',None),
        files={path.name:digest(path.read_bytes()) for path in output.iterdir() if path.is_file()},
        elapsed_seconds=time.perf_counter()-started)
    write_json(output/'manifest.json',result)
    return result
