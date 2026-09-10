"""Cached native evidence agrees with full checks through adversarial edits."""
from pathlib import Path
import tempfile
import unittest

import cadquery as cq

from stud.cad import Model
from stud.checks import check_model
from stud.contracts import read_json,write_json


class QueryCacheTests(unittest.TestCase):
    def test_cached_evidence_cannot_bypass_mixed_requirement_unit_rejection(self):
        model=Model('Native inches',units='in')
        model.part('board',cq.Workplane('XY').box(1.5,3.5,24,centered=(False,False,False)),blank={'size':[1.5,3.5,24]})
        model.requirement('good','stock_fit',['board'])
        self.assertTrue(check_model(model,cache_path=self.path)['all_passed'])
        model.requirement('wrong','stock_fit',['board'],units='mm3')
        self.assert_full_agreement(model)
        findings=check_model(model,cache_path=self.path)['findings']
        self.assertEqual(findings[-1]['status'],'execution_failed')
        self.assertEqual(findings[-1]['error']['category'],'unit_mismatch')

    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.path=Path(temporary.name)/'queries.json'

    def fixture(self, *, hole_x=20,move=0,blank=100,direction=(0,0,-1),threshold=1,remove=False):
        model=Model('Native cache fixture')
        top=cq.Workplane('XY').box(100,60,12,centered=(False,False,False))
        top=top.cut(cq.Workplane('XY').center(hole_x,30).circle(5).extrude(15))
        model.part('top',top,blank={'size':[blank,60,12]},location=cq.Location(cq.Vector(0,0,40)))
        model.requirement('top.stock','stock_fit',['top'])
        if not remove:
            model.part('support',cq.Workplane('XY').box(100,60,40,centered=(False,False,False)),location=cq.Location(cq.Vector(move,0,0)),blank={'size':[100,60,40]})
            model.requirement('support.stock','stock_fit',['support'])
        model.requirement('bearing','support',['top','support'],threshold=threshold,direction=list(direction))
        model.requirement('edges','panel_edge_support',['top','support'],threshold=0,direction_local=[0,0,-1])
        return model

    def assert_full_agreement(self,model):
        cached=check_model(model,cache_path=self.path)
        full=check_model(model,reuse=False)
        self.assertEqual(cached['findings'],full['findings'])
        self.assertEqual(cached['coverage'],full['coverage'])
        self.assertEqual(cached['all_passed'],full['all_passed'])
        return cached

    def test_shape_placement_blank_policy_threshold_deletion_and_restore(self):
        first=self.assert_full_agreement(self.fixture())
        repeated=self.assert_full_agreement(self.fixture())
        self.assertGreater(sum(row.get('cache_hits',0) for row in repeated['timings'].values()),0)
        for arguments in (dict(hole_x=70),dict(move=25),dict(blank=80),dict(direction=(1,0,0)),dict(threshold=10000),dict(remove=True),{}):
            with self.subTest(arguments=arguments):self.assert_full_agreement(self.fixture(**arguments))
        self.assertTrue(first['coverage']['complete'])

    def test_corrupt_cache_is_discarded_and_full_mode_bypasses_it(self):
        self.assert_full_agreement(self.fixture())
        stored=read_json(self.path)
        for value in stored['entries'].values():value[0]=999999
        write_json(self.path,stored)
        result=self.assert_full_agreement(self.fixture())
        self.assertFalse(any(row.get('cache_hits') for row in result['timings'].values()))
        full=check_model(self.fixture(),cache_path=self.path,reuse=False)
        self.assertFalse(any(row.get('cache_hits') for row in full['timings'].values()))

    def test_malformed_disposable_cache_does_not_interrupt_checking(self):
        for value in (None,[],1,'invalid',dict(schema_version=1,entries=[])):
            with self.subTest(value=value):
                write_json(self.path,value)
                self.assert_full_agreement(self.fixture())
