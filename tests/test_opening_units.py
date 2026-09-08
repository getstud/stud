import copy
import unittest
from stud import WallFrame, door_unit, window_unit
from test_opening_assemblies import opening_project
from validate import validate


def failures(p):
    return [f for f in validate(p.export()) if f['status']=='FAIL']


def unit_project(angle=0,inward=1):
    p,o=opening_project(start=24,width=38,bottom=0,height=82,field_studs=[],frame=WallFrame((13,-24,7),angle,inward))
    p.stock('unit','Product','#aaa',product=True,purchase_unit='unit')
    return p,o


class UnitTests(unittest.TestCase):
    def test_doors_fit_and_open_in_transformed_hosts(self):
        for angle in (0,90,37):
            for inward in (-1,1):
                for hand in ('left','right'):
                    for swing in ('in','out'):
                        p,o=unit_project(angle,inward)
                        u=door_unit(p,'door',opening=o,product_stock='unit',frame_depth=4.5,inset=-.5,hand=hand,swing=swing,obstacle_ids=list(o.roles.values()))
                        self.assertFalse(failures(p),failures(p))
                        row=next(r for r in p.export()['materials'] if r['stock']=='unit')
                        self.assertEqual(row['quantity'],1)
                        self.assertEqual(row['kind'],'product')

    def test_windows_fit_and_operate(self):
        for angle in (0,37,90):
            for inward in (-1,1):
                for operation in ('fixed','casement','slider'):
                    p,o=unit_project(angle,inward)
                    window_unit(p,'win',opening=o,product_stock='unit',frame_depth=4.5,inset=-.5,operation=operation,obstacle_ids=list(o.roles.values()))
                    self.assertFalse(failures(p),failures(p))

    def test_moving_leaf_obstruction_and_removed_member_fail(self):
        p,o=unit_project()
        p.stock('obstacle','obstacle','#aaa',section=(1.5,3.5),lengths=(96,))
        p.box('obstacle','Fixture','obstacle',**o.frame.box((25,10,0),(1.5,3.5,80)))
        u=door_unit(p,'door',opening=o,product_stock='unit',frame_depth=3.5,open_angles=(90,),obstacle_ids=['obstacle'])
        self.assertTrue(any(f.get('rule_id')=='door.open.0' for f in failures(p)))
        p.parts[:]=[part for part in p.parts if part['id']!=u.roles['head']]
        self.assertTrue(any(f.get('rule_id')=='door.members' for f in failures(p)))

    def test_host_depth_input_and_geometry_are_independent(self):
        p,o=unit_project();before=copy.deepcopy(p.__dict__)
        with self.assertRaises(ValueError):door_unit(p,'door',opening=o,product_stock='unit',frame_depth=3.5,inset=100)
        self.assertEqual(p.__dict__,before)
        u=door_unit(p,'door',opening=o,product_stock='unit',frame_depth=3.5)
        for part in p.parts:
            if part['id'] in u.part_ids:part['origin'][1]+=100
        self.assertTrue(any(f.get('rule_id')=='door.host_depth' for f in failures(p)))
