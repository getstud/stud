"""Information and physical placement that compacting a workshop packet must retain."""
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cadquery as cq
from pypdf import PdfReader

from stud.cad import Model
from stud.contracts import StudError
from stud.estimate import calculate
from stud.plans import format_length, generate
from stud.plans_compact import CompactPacket, cut_groups


class CompactPlansTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='stud-compact-test-')
        self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)

    def packet(self,model,review=None):
        manifest=model.export()
        manifest.update(build_id='test-build',project_id='test-project',source_id='test-source',runtime={'id':'test'},
                        completion={'geometry':'complete','checks':'complete','quantities':'complete'})
        review=review or dict(status='review',geometry='complete',findings=[],dimensions={})
        estimate=calculate(manifest['demands'],{})
        return CompactPacket(model,manifest,self.directory,'test-checkpoint',{'units':'imperial' if model.units=='in' else 'mm'},review,estimate)

    def test_hidden_equal_volume_edit_and_material_specification_do_not_collapse(self):
        model=Model('Distinct parts')
        box=cq.Workplane('XY').box(100,100,10,centered=(False,False,False))
        blank=dict(size=[100,100,10],operations=[dict(kind='panel_cut',finished_size=[100,100])])
        left=box.cut(cq.Workplane('XY').center(20,50).circle(5).extrude(10))
        right=box.cut(cq.Workplane('XY').center(80,50).circle(5).extrude(10))
        for key,shape in [('left',left),('copy',left),('right',right),('other_grade',left)]:
            model.part(key,shape,blank=blank,material='plywood')
            model.demand(key,product_id='plywood',specification={'grade':'B' if key=='other_grade' else 'A'},object_ids=[key],quantity=1)
        groups,labels=cut_groups(model)
        self.assertAlmostEqual(model.shapes['left']['local'].Volume(),model.shapes['right']['local'].Volume())
        self.assertEqual(labels['left'],labels['copy'])
        self.assertNotEqual(labels['left'],labels['right'])
        self.assertNotEqual(labels['left'],labels['other_grade'])
        self.assertEqual(sorted(len(g['objects']) for g in groups),[1,1,2])

    def test_shorter_finished_cuts_and_material_specs_survive_pdf_and_csv(self):
        model=Model('Finished cuts')
        model.part('rail',cq.Workplane('XY').box(600,38,89,centered=(False,False,False)),material='lumber',
            blank=dict(size=[700,38,89],operations=[dict(kind='square_cut',finished_length=600)]))
        model.part('panel',cq.Workplane('XY').box(80,70,10,centered=(False,False,False)),material='plywood',
            blank=dict(size=[100,100,10],panel_axes=[0,1],operations=[dict(kind='panel_cut',finished_size=[80,70])]))
        model.demand('rail_stock',product_id='lumber',specification={'species':'Douglas fir','grade':'No. 2','section':[38,89]},
            object_ids=['rail'],unit='mm',purchase_unit='board',stock_lengths=[2400],cuts=[dict(object_id='rail',length=700)])
        model.demand('panel_stock',product_id='plywood',specification={'grade':'Exterior','thickness':10},object_ids=['panel'],quantity=1)
        model.drawing('front',objects=['rail'])
        packet=self.packet(model)
        with patch('stud.plans.load_model',return_value=(model,packet.manifest)):
            result=generate('unused',self.directory/'export',checkpoint='test-checkpoint',print_spec={'units':'mm'},estimate=packet.estimate)
        text='\n'.join(page.extract_text() for page in PdfReader(self.directory/'export'/'plans.pdf').pages)
        for value in ('finish length 600 mm','finish panel 80 mm','70 mm','Douglas fir','No. 2','Exterior','C01/M01','C02/M02'):
            self.assertIn(value,text)
        with (self.directory/'export'/'parts.csv').open() as stream:rows=list(csv.DictReader(stream))
        self.assertEqual([(r['part_id'],r['cut_label'],r['material']) for r in rows],[('rail','C01','lumber'),('panel','C02','plywood')])
        self.assertEqual(sum(len(g['objects']) for g in result['grouped_inventory']['cuts']),2)

    def test_sheet_finished_profile_retains_its_offset_inside_the_blank(self):
        model=Model('Offset finished panel')
        model.part('panel',cq.Workplane('XY').box(80,70,10,centered=(False,False,False)).translate((20,30,0)),material='plywood',
            blank=dict(size=[100,100,10],panel_axes=[0,1],operations=[dict(kind='panel_cut',finished_size=[80,70])]))
        model.demand('sheets',product_id='plywood',specification={'thickness':10},object_ids=['panel'],quantity=1,
            sheets=[dict(id='sheet',size=[200,200],panels=[dict(object_id='panel',origin=[40,50],size=[100,100])])])
        packet=self.packet(model)
        from stud.plans_compact import renderPDF
        with patch.object(renderPDF,'draw',wraps=renderPDF.draw) as drawn:packet.compact_sheets()
        layout=packet.pages[0]['layouts'][0];factor=72/25.4/layout['scale_denominator']
        self.assertAlmostEqual(drawn.call_args.args[2],layout['bounds_points'][0]+60*factor)
        self.assertAlmostEqual(drawn.call_args.args[3],layout['bounds_points'][1]+80*factor)
        packet.canvas.save()

    def test_crowded_dimensions_fail_instead_of_crossing_the_page_header(self):
        model=Model('Dimensions');model.part('part',cq.Workplane('XY').box(100,10,10))
        dimensions={str(i):dict(id=str(i),value=100,start_point=[-50,0,0],end_point=[50,0,0]) for i in range(13)}
        packet=self.packet(model,dict(status='complete',geometry='complete',findings=[],dimensions=dimensions))
        packet.new_page('Test','drawing',views=[])
        with self.assertRaises(StudError) as error:
            packet.view_panel(dict(id='front',label='Front',direction=[0,-1,0],up=[0,0,1],dimensions=list(dimensions)),36,400,260,260)
        self.assertEqual(error.exception.category,'plan_layout')

    def test_identical_step_text_keeps_every_exploded_assembly(self):
        model=Model('Repeated steps');shape=cq.Workplane('XY').box(100,30,20)
        for i in range(3):
            key=f'part_{i}';model.part(key,shape,location=cq.Location(cq.Vector(i*200,0,0)))
            model.step(f'assemble_{i}','Fasten the frame.',parts=[key],exploded={key:[0,0,50]})
        packet=self.packet(model);packet.assembly_steps();packet.close_page();packet.canvas.save()
        self.assertEqual(len(packet.inventory['steps']),1)
        illustrations=[item for page in packet.pages for item in page.get('illustrations',[])]
        self.assertEqual({i['step_id'] for i in illustrations},{'assemble_0','assemble_1','assemble_2'})
        self.assertEqual(len(list(self.directory.glob('step-*.svg'))),3)

    def test_imperial_dimensions_keep_units_and_cut_precision(self):
        self.assertEqual(format_length(1.5),'1 1/2 in')
        self.assertEqual(format_length(-1.5),'-1 1/2 in')
        self.assertEqual(format_length(.125),'1/8 in')
        self.assertEqual(format_length(38.1,'mm'),'38.1 mm')
        for value in (3.12345,12.0009,38.5555,-19.9021):
            text=format_length(value)
            self.assertNotIn('mm',text)
            self.assertLessEqual(abs(float(text.removesuffix(' in'))-value),.000051)

    def test_imperial_pdf_sheet_and_instructions_have_an_exact_four_inch_scale(self):
        import runpy
        workbench=runpy.run_path(str(Path(__file__).resolve().parents[1]/'examples/cadquery-workbench/workbench.py'))['workbench']
        model=Model('Imperial bench',units='in');workbench(model,dog_hole=(8,4))
        packet=self.packet(model)
        for layout in ('compact','expanded'):
            with self.subTest(layout=layout),patch('stud.plans.load_model',return_value=(model,packet.manifest)):
                directory=self.directory/layout
                result=generate('unused',directory,checkpoint='test-checkpoint',
                    print_spec={'units':'imperial','layout':layout},estimate=packet.estimate)
                reader=PdfReader(directory/'plans.pdf')
                text='\n'.join(page.extract_text() for page in reader.pages)
                self.assertNotRegex(text,r'\bmm\b')
                for value in ('3/4 in','1/8 in','8 in','Scale check: this line is exactly 4 in'):
                    self.assertIn(value,text)
                for sheet,page in zip(result['sheets'],reader.pages):
                    self.assertEqual(sheet['calibration']['length_points'],288)
                    import math
                    self.assertAlmostEqual(math.dist(sheet['calibration']['start'],sheet['calibration']['end']),288)
                    # Verify the actual PDF drawing operators, not just metadata.
                    from pypdf.generic import ContentStream
                    operations=ContentStream(page.get_contents(),reader).operations
                    start,end=sheet['calibration']['start'],sheet['calibration']['end']
                    self.assertTrue(any(op==b'm' and list(args)==start and next_op==b'l' and list(next_args)==end
                        for (args,op),(next_args,next_op) in zip(operations,operations[1:])))

    def test_hardware_sizes_and_unfamiliar_purchase_properties_are_printed(self):
        model=Model('Hardware')
        for length in (40,80):
            model.demand(f'screws_{length}',product_id='screws',specification={'type':'wood screw','diameter':5,'length':length,
                'treatment':'Exterior rated'},object_ids=[],quantity=20)
        packet=self.packet(model);packet.new_page('Materials','materials');packet.purchase_lists();packet.close_page();packet.canvas.save()
        text='\n'.join(page.extract_text() for page in PdfReader(self.directory/'plans.pdf').pages)
        for expected in ('diameter: 5 mm','length: 40 mm','length: 80 mm','Exterior rated'):self.assertIn(expected,' '.join(text.split()))

    def test_deleted_cut_targets_leave_an_inspectable_review_packet(self):
        model=Model('Deleted targets')
        model.demand('sheet',product_id='plywood',specification={'thickness':10},object_ids=['deleted_panel'],quantity=1,
            sheets=[dict(id='sheet',size=[200,200],panels=[dict(object_id='deleted_panel',origin=[0,0],size=[100,100])])])
        model.demand('board',product_id='lumber',specification={'section':[38,89]},object_ids=['deleted_rail'],
            unit='mm',purchase_unit='board',stock_lengths=[2400],cuts=[dict(object_id='deleted_rail',length=700)])
        packet=self.packet(model);packet.new_page('Purchases','materials');packet.purchase_lists();packet.compact_sheets();packet.canvas.save()
        text='\n'.join(page.extract_text() for page in PdfReader(self.directory/'plans.pdf').pages)
        self.assertIn('Missing: deleted_rail',text)
        self.assertIn('Missing part',text)
        self.assertEqual(packet.inventory['sheets'][0]['panels'][0]['label'],'Missing: deleted_panel')

    def test_material_legend_does_not_depend_on_a_saved_estimate(self):
        model=Model('Unpriced joinery')
        model.part('rail',cq.Workplane('XY').box(600,38,89),material='lumber')
        model.demand('stock',product_id='lumber',specification={'species':'oak','grade':'select'},object_ids=['rail'],quantity=1)
        packet=self.packet(model);packet.estimate=None;packet.lists();packet.canvas.save()
        text='\n'.join(page.extract_text() for page in PdfReader(self.directory/'plans.pdf').pages)
        for expected in ('C01/M01','oak','select','estimate unavailable'):self.assertIn(expected,text)
