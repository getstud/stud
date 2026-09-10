"""Project dimensions survive native evaluation, measurement, quoting and export."""
import math
import csv
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import cadquery as cq
from pypdf import PdfReader

from stud.cad import Model
from stud.checks import check_model
from stud.contracts import StudError, read_json, write_json
from stud.display import model_for_viewer
from stud.estimate import quote_key
from stud.evaluated import load_model
from stud.history import History, initialize
from stud.session import Session
from stud_cli import init_project


def board_source(units):
    # These are independently authored dimensions for the same physical board.
    width,depth,length,x,y=(1.5,3.5,24,10,20) if units=='in' else (38.1,88.9,609.6,254,508)
    stock=96 if units=='in' else 2438.4
    return f'''import cadquery as cq
from stud.cad import Model
model=Model('Exact stock',units={units!r})
model.part('board',cq.Workplane('XY').box({width},{depth},{length},centered=(False,False,False)),
    location=cq.Location(cq.Vector({x},{y},0)),material='lumber',
    blank={{'size':[{width},{depth},{length}],'cut_length':{length},'operations':[{{'kind':'square_cut','finished_length':{length}}}]}})
model.reference('board','left',point=(0,0,0))
model.reference('board','right',point=({width},0,0))
model.requirement('width','length',['board:left','board:right'],threshold={width})
model.requirement('blank','stock_fit',['board'])
model.demand('stock',product_id='lumber',specification={{'section':[{width},{depth}]}},object_ids=['board'],
    unit={units!r},purchase_unit='board',stock_lengths=[{stock}],cuts=[{{'object_id':'board','length':{length}}}])
model.dimension('width','board:left','board:right',label='Board thickness')
model.drawing('end',direction=(0,0,1),up=(0,1,0),dimensions=['width'])
model.step('cut','Cut the board to the listed length.',parts=['board'],view='end')
'''


class NativeUnitsTests(unittest.TestCase):
    def test_real_worker_preserves_inch_and_metric_dimensions(self):
        with tempfile.TemporaryDirectory() as temporary:
            for units,width,depth,length,x,y in [('in',1.5,3.5,24,10,20),('mm',38.1,88.9,609.6,254,508)]:
                with self.subTest(units=units):
                    root=Path(temporary)/units;root.mkdir()
                    (root/'design.py').write_text(board_source(units),encoding='utf-8')
                    initial=initialize(root,units=units)
                    with Session(root) as session:
                        request=session.begin(key='board',expected_head=initial['checkpoint'],intent='Inspect exact stock')
                        project_file=Path(request['workspace'])/'stud.json'
                        project_manifest=read_json(project_file)
                        # Omitted optional settings must retain native defaults.
                        project_manifest['evaluation']={'deterministic':False}
                        write_json(project_file,project_manifest)
                        source=session.source(request['id'])['source_id']
                        result=session.wait(session.finish(request['id'],expected_source=source,summary='Exact stock')['id'],timeout=60)
                        self.assertEqual(result['status'],'complete',result)
                        build=session.job(result['build_id']);archive=Path(build['artifact_path'])
                        model,manifest=load_model(archive)
                        obj=manifest['objects'][0];asset=manifest['assets'][obj['shape_key']]
                        self.assertEqual(manifest['units'],units);self.assertEqual(asset['units'],units)
                        self.assertEqual(obj['blank']['size'],[width,depth,length])
                        self.assertEqual([obj['placement'][i][3] for i in range(3)],[x,y,0])
                        self.assertAlmostEqual(model.shapes['board']['local'].BoundingBox().xlen,width)
                        self.assertAlmostEqual(model.shapes['board']['local'].Volume(),width*depth*length,places=5)
                        mesh=(archive/asset['mesh']).read_bytes();vertices=struct.unpack_from('<I',mesh,8)[0]
                        xs=[struct.unpack_from('<f',mesh,16+i*12)[0] for i in range(vertices)]
                        self.assertAlmostEqual(max(xs)-min(xs),width,places=5)
                        findings={f['requirement_id']:f for f in manifest['checks']['findings']}
                        self.assertEqual(findings['width']['units'],units)
                        self.assertAlmostEqual(findings['width']['measured'],width)
                        self.assertEqual(findings['blank']['units'],units+'3')
                        measured=session.wait(session.measure(key='measure',build_id=build['id'],targets=['board:left','board:right'])['id'])
                        self.assertEqual(measured['status'],'complete',measured)
                        self.assertEqual(measured['result']['units'],units)
                        self.assertAlmostEqual(measured['result']['value'],width)
                        picked=session.wait(session.measure(key='pick',build_id=build['id'],targets=[
                            {'object_id':'board','point':[x,y,0]}, {'object_id':'board','point':[x+width,y,0]}])['id'])
                        self.assertEqual(picked['status'],'complete',picked)
                        self.assertAlmostEqual(picked['result']['value'],width)
                        valid=session.wait(session.measure(key='valid',build_id=build['id'],kind='solid_valid',targets=['board'])['id'])
                        self.assertEqual(valid['status'],'complete',valid)
                        self.assertEqual(valid['result']['units'],'boolean')
                        self.assertEqual(valid['result']['value'],1)
                        viewer=model_for_viewer(session)
                        self.assertEqual(viewer['display_units'],units)
                        self.assertEqual(viewer['parts'][0]['cad']['units'],units)
                        for actual,expected in zip(viewer['parts'][0]['size'],[1.5,3.5,24]):self.assertAlmostEqual(actual,expected)
                        packet=session.wait(session.plans(key='packet',checkpoint=result['checkpoint'],build_id=build['id'],
                            print_spec={'scale':1},include_lists=False)['id'])
                        self.assertEqual(packet['status'],'complete',packet)
                        dimension=packet['result']['sheets'][0]['dimensions'][0]
                        self.assertAlmostEqual(math.dist(dimension['start'],dimension['end']),108)
                        text='\n'.join(page.extract_text() for page in PdfReader(packet['result']['pdf']).pages)
                        self.assertIn('1 1/2 in' if units=='in' else '38.1 mm',text)
                        self.assertNotIn(' mm' if units=='in' else ' in',text)
                        with (Path(packet['result']['pdf']).parent/'parts.csv').open() as stream:
                            self.assertEqual(next(csv.DictReader(stream))['units'],units)
                        wrong=session.wait(session.plans(key='wrong-units',checkpoint=result['checkpoint'],
                            print_spec={'units':'mm' if units=='in' else 'imperial'})['id'])
                        self.assertEqual(wrong['error']['category'],'unit_mismatch')

    def test_initializing_in_existing_git_history_keeps_native_units(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=board_source('in')
            (root/'design.py').write_text(source,encoding='utf-8')
            history=History(root);history.git('init')
            original=history.commit(None,{'design.py':source.encode()},[],'Original project',history.author(),1700000000)
            history.git('update-ref','refs/heads/main',original)
            history.git('symbolic-ref','HEAD','refs/heads/main');history.git('read-tree',original)
            initialized=initialize(root,units='in')
            self.assertEqual(history.head(),original)
            with Session(root) as session:
                self.assertEqual(session.manifest['units'],'in')
                self.assertEqual(session.snapshot()['option']['head'],initialized['checkpoint'])

    def test_packet_audits_apply_native_linear_and_volume_tolerances(self):
        from stud.plans import preflight
        from stud.plans_compact import cut_groups
        for units,scale in [('in',1),('mm',25.4)]:
            with self.subTest(units=units):
                model=Model('Small differences',units=units)
                box=cq.Workplane('XY').box(1.5*scale,3.5*scale,scale,centered=(False,False,False))
                hole=cq.Workplane('XY').center(.5*scale,.5*scale).circle(.01*scale).extrude(scale)
                blank={'size':[1.5*scale,3.5*scale,scale],'operations':[{'kind':'panel_cut'}]}
                model.part('solid',box,blank=blank);model.part('bored',box.cut(hole),blank=blank)
                # The small bore must not disappear when grouping equal blanks.
                groups,_=cut_groups(model);self.assertEqual(len(groups),2)
                model.reference('solid','a',point=(0,0,0));model.reference('solid','b',point=(1.5*scale,0,0))
                model.dimension('width','solid:a','solid:b',expected=1.505*scale)
                model.demand('panels',product_id='panel',specification={'thickness':scale,'sheet':[1.5*scale,3.5*scale]},
                    object_ids=['solid'],sheets=[{'id':'sheet','size':[1.5*scale,3.5*scale],
                        'panels':[{'object_id':'solid','origin':[.005*scale,0],'size':[1.5*scale,3.5*scale]}]}])
                manifest=model.export();manifest['completion']={'geometry':'complete','checks':'complete','quantities':'complete'}
                findings=preflight(model,manifest)['findings'];categories={item['category'] for item in findings}
                self.assertIn('stale_dimension',categories);self.assertIn('sheet_fit',categories)

    def test_units_cannot_change_in_a_draft_or_when_reopening(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'design.py').write_text(board_source('in'),encoding='utf-8')
            initial=initialize(root,units='in')
            with Session(root) as session:
                request=session.begin(key='edit',expected_head=initial['checkpoint'],intent='Change units')
                file=Path(request['workspace'])/'stud.json';manifest=read_json(file);manifest['units']='mm';write_json(file,manifest)
                for action in [lambda:session.source(request['id']),lambda:session.evaluate(request['id']),
                               lambda:session.finish(request['id'],expected_source=None,summary='Invalid unit edit')]:
                    with self.assertRaises(StudError) as error:action()
                    self.assertEqual(error.exception.category,'unit_mismatch')
            file=root/'stud.json';manifest=read_json(file);manifest['units']='mm';write_json(file,manifest)
            with self.assertRaises(StudError) as error:Session(root)
            self.assertEqual(error.exception.category,'unit_mismatch')

    def test_real_worker_rejects_model_unit_reassignment(self):
        with tempfile.TemporaryDirectory() as temporary:
            for units,other in [('in','mm'),('mm','in')]:
                root=Path(temporary)/units;root.mkdir()
                (root/'design.py').write_text(board_source(units),encoding='utf-8')
                initial=initialize(root,units=units)
                with Session(root) as session:
                    for after_part in (False,True):
                        with self.subTest(units=units,after_part=after_part):
                            request=session.begin(key=str(after_part),expected_head=initial['checkpoint'],intent='Reject changed units')
                            source_text=f"import cadquery as cq\nfrom stud.cad import Model\nmodel=Model('Fixed units',units={units!r})\nmodel.part('board',cq.Workplane('XY').box(1,2,3))\nmodel.requirement('valid','solid_valid',['board'])\n"
                            assignment=f'model.units={other!r}\n'
                            source_text=source_text+assignment if after_part else source_text.replace("model.part('board',",assignment+"model.part('board',",1)
                            (Path(request['workspace'])/'design.py').write_text(source_text,encoding='utf-8')
                            source=session.source(request['id'])['source_id']
                            build=session.wait(session.evaluate(request['id'],source)['id'],timeout=60)
                            try:
                                self.assertEqual(build['status'],'generation_failed',build)
                                manifest=read_json(Path(build['artifact_path'])/'manifest.json')
                                self.assertEqual(manifest['units'],units)
                                self.assertNotEqual(manifest['completion']['geometry'],'complete')
                                self.assertIn('units are fixed',manifest['diagnostics']['message'])
                                self.assertTrue(all(asset['units']==units for asset in manifest['assets'].values()))
                            finally:session.cancel(request['id'])

    def test_cli_creates_native_inch_default_and_explicit_metric(self):
        with tempfile.TemporaryDirectory() as temporary,patch('stud_cli.register'):
            for units in ('in','mm'):
                root=Path(temporary)/units
                init_project(root,**({} if units=='in' else {'units':'mm'}))
                self.assertEqual(read_json(root/'stud.json')['units'],units)
                namespace={};exec((root/'design.py').read_text(),namespace)
                model=namespace['model']
                self.assertEqual(model.units,units)
                self.assertEqual(model.objects['starter']['blank']['size'],[24,1.5,3.5] if units=='in' else [600,38,89])
                self.assertTrue(check_model(model)['all_passed'])
            with self.assertRaises(ValueError):init_project(Path(temporary)/'wrong',units='mm',example='workbench')
            self.assertFalse((Path(temporary)/'wrong').exists())

    def test_mixed_stock_and_requirement_units_are_explicit_errors(self):
        model=Model('inches',units='in');model.part('board',cq.Workplane('XY').box(1.5,3.5,24))
        with self.assertRaises(StudError):model.demand('wrong',product_id='wood',specification={},object_ids=['board'],unit='mm')
        with self.assertRaises(StudError):model.demand('wrong',product_id='wood',specification={'length_unit':'mm'},object_ids=['board'])
        model.reference('board','a',point=(0,0,0));model.reference('board','b',point=(1.5,0,0))
        model.requirement('wrong','length',['board:a','board:b'],threshold=1.5,units='mm')
        finding=check_model(model)['findings'][0]
        self.assertEqual(finding['status'],'execution_failed')
        self.assertEqual(finding['error']['category'],'unit_mismatch')
        shared=dict(product_id='wood',purchase_unit='each',specification={'length':1.5})
        self.assertNotEqual(quote_key({**shared,'specification':{'length':1.5,'length_unit':'in'}}),quote_key(shared))
