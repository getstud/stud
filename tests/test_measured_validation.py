import copy
import math
import unittest
from solid_geometry import solids, collision, contact_area, volume, bounds
from validation_rules import Context, evaluate, coverage
from validate import validate


def box(pid,size=(2,2,2),origin=(0,0,0),rotation=(0,0,0),**extra):
    return dict(id=pid,assembly='Frame',stock='wood',size=list(size),origin=list(origin),rotation=list(rotation),cut_length=None,**extra)


def model(*parts):
    return dict(parts=list(parts),stocks={'wood':{}},validation={'version':1,'rules':[]})


def run(rule,*parts):return evaluate(Context(model(*parts)),rule)


class SolidTests(unittest.TestCase):
    def test_face_touching_is_not_collision(self):
        self.assertIsNone(collision(solids(box('a')),solids(box('b',origin=(2,0,0)))))
        self.assertIsNotNone(collision(solids(box('a')),solids(box('b',origin=(1.75,0,0)))))

    def test_rotated_boxes_with_overlapping_bounds_but_no_collision(self):
        a=box('a',(10,1,1),rotation=(0,0,45))
        b=box('b',(10,1,1),origin=(-1,1,0),rotation=(0,0,45))
        aa,bb=bounds(solids(a)),bounds(solids(b))
        self.assertTrue(all(min(x[1],y[1])>max(x[0],y[0]) for x,y in zip(aa,bb)))
        self.assertIsNone(collision(solids(a),solids(b)))
        b['origin']=[-.25,.25,0]
        self.assertIsNotNone(collision(solids(a),solids(b)))

    def test_profiles_and_rotations_preserve_volume(self):
        p=box('p',(2,10,9),rotation=(20,35,50),profile={'bottom':[0,5],'top':[4,9]})
        self.assertAlmostEqual(sum(volume(s) for s in solids(p)),80)

    def test_notch_clears_member_and_detects_intrusion(self):
        stud=box('stud',(3.5,1.5,20),profile={'bottom':[0,0],'top':[20,20],'notch':{'side':'max','depth':1.5,'top':[12,12]}})
        rafter=box('r',(1.5,1.5,8),(2,0,12))
        self.assertIsNone(collision(solids(stud),solids(rafter)))
        self.assertAlmostEqual(sum(volume(s) for s in solids(stud)),87)
        self.assertAlmostEqual(contact_area(solids(stud),solids(rafter))[0],14.25)
        rafter['origin'][0]-=.125
        self.assertIsNotNone(collision(solids(stud),solids(rafter)))

    def test_seat_removes_only_requested_region(self):
        r=box('r',(2,10,4),seats=[{'y':[0,3],'z':1}])
        support=box('support',(2,3,2),(0,0,-1))
        self.assertAlmostEqual(sum(volume(s) for s in solids(r)),74)
        self.assertIsNone(collision(solids(r),solids(support)))
        self.assertAlmostEqual(contact_area(solids(r),solids(support),direction=(0,0,-1))[0],6)

    def test_nonfinite_transform_is_rejected(self):
        with self.assertRaises(ValueError):solids(box('p',origin=(float('nan'),0,0)))

    def test_bad_notch_rejected(self):
        p=box('p',profile={'bottom':[0,0],'top':[2,2],'notch':{'side':'max','depth':3,'top':[1,1]}})
        with self.assertRaises(ValueError):solids(p)


class RuleTests(unittest.TestCase):
    def test_minimum_contact_catches_line_touch_and_small_bearing(self):
        plate=box('plate',(4,2,2))
        r=box('r',(4,2,4),(0,0,2),profile={'bottom':[0,2],'top':[2,4]})
        rule={'kind':'minimum_contact','parts':['r','plate'],'minimum_area':2,'normal':[0,0,-1]}
        self.assertEqual(run(rule,r,plate)[0]['status'],'FAIL')
        r=box('r',(4,2,2),(3.5,0,2))
        f=run(rule,r,plate)[0]
        self.assertEqual(f['measured']['contact_area_sq_in'],1)
        self.assertEqual(f['status'],'FAIL')
        r['origin'][0]=3
        self.assertEqual(run(rule,r,plate)[0]['status'],'PASS')

    def test_contact_requires_opposed_normals_and_no_penetration(self):
        a,b=box('a'),box('b',origin=(0,0,1.9))
        self.assertEqual(contact_area(solids(a),solids(b))[0],0)

    def test_alignment_reports_signed_error_and_tolerance(self):
        a,b=box('a'),box('b',origin=(5,0,.5))
        f=run({'kind':'face_alignment','parts':['a','b'],'axis':2},a,b)[0]
        self.assertEqual(f['measured']['error_in'],.5)
        self.assertEqual(f['status'],'FAIL')
        b['origin'][2]=.0001
        self.assertEqual(run({'kind':'face_alignment','parts':['a','b'],'axis':2},a,b)[0]['status'],'PASS')

    def test_opening_ignores_touching_jamb_but_detects_stud(self):
        jamb=box('jamb',(1,2,10),(-1,0,0));stud=box('stud',(1,2,10),(3,0,0))
        rule={'kind':'opening_clearance','parts':['jamb','stud'],'opening':{'size':[6,2,8],'origin':[0,0,0]}}
        f=run(rule,jamb,stud)
        self.assertEqual([x['parts'] for x in f if x['status']=='FAIL'],[['stud']])

    def test_collision_exception_needs_reason_and_stays_visible(self):
        a,b=box('a'),box('b',origin=(1,0,0))
        rule={'kind':'solid_collision','parts':['a','b'],'exceptions':[{'parts':['a','b'],'reason':'Intentional half-lap awaiting joinery model'}]}
        self.assertEqual(run(rule,a,b)[0]['status'],'WARNING')
        rule['exceptions'][0]['reason']=''
        with self.assertRaises(ValueError):run(rule,a,b)

    def test_panel_support_missing_edge_and_duplicate_support_area(self):
        p=box('panel',(10,10,1),(0,0,2));s=box('support',(10,10,2))
        rule={'kind':'panel_support','parts':['panel','support'],'bearing_width':.75}
        self.assertTrue(all(f['status']=='PASS' for f in run(rule,p,s)))
        s['size'][0]=5
        f=run(rule,p,s)
        self.assertTrue(any(x['status']=='FAIL' for x in f))
        duplicate=copy.deepcopy(s);duplicate['id']='duplicate'
        rule['parts'].append('duplicate')
        f2=run(rule,p,s,duplicate)
        self.assertEqual([x['measured'] for x in f],[x['measured'] for x in f2])

    def test_panel_support_respects_rotation(self):
        # Local panel underside is world -X after rotating around Y.
        p=box('panel',(10,10,1),(-4.5,0,4.5),(0,90,0))
        s=box('support',(2,10,10),(-2,0,0))
        f=run({'kind':'panel_support','parts':['panel','support'],'bearing_width':.75},p,s)
        self.assertTrue(all(x['status']=='PASS' for x in f),f)

    def test_stock_fit_checks_both_sheet_dimensions(self):
        p=box('sheet',(49,95,.5));m=model(p);m['stocks']['wood']={'sheet':[48,96]}
        f=evaluate(Context(m),{'kind':'stock_fit','parts':['sheet']})
        self.assertEqual(f[0]['status'],'FAIL')

    def test_stock_fit_catches_stale_lumber_length(self):
        p=box('stud',(1.5,3.5,91.5));p['cut_length']=80
        m=model(p);m['stocks']['wood']={'section':[1.5,3.5],'lengths':[96]}
        self.assertEqual(evaluate(Context(m),{'kind':'stock_fit','parts':['stud']})[0]['status'],'FAIL')

    def test_automatic_checks_and_separate_coverage(self):
        m=model(box('a'),box('b',origin=(3,0,0)))
        m['validation']['automatic']=['solid_collision']
        f=validate(m);c=coverage(m,f)
        self.assertEqual(c['checked_parts'],2)
        self.assertEqual(c['assemblies'][0]['categories']['support'],0)
        self.assertEqual(c['assemblies'][0]['categories']['collisions'],2)

    def test_empty_scope_does_not_pass(self):
        m=model(box('a'));m['validation']['rules']=[{'kind':'minimum_contact','parts':[],'minimum_area':1}]
        self.assertTrue(any(f['status']=='FAIL' for f in validate(m)))

    def test_missing_part_reference_fails(self):
        m=model(box('a'));m['validation']['rules']=[{'kind':'face_alignment','parts':['a','missing'],'axis':2}]
        self.assertTrue(any(f['status']=='FAIL' for f in validate(m)))


class CoverageIntegrityTests(unittest.TestCase):
    def test_duplicate_ids_fail_before_rules_run(self):
        self.assertEqual(validate(model(box('same'),box('same')))[0]['status'],'FAIL')

    def test_unsupported_panel_is_not_counted_as_support_checked(self):
        panel=box('p',profile={'bottom':[0,0],'top':[1,2]});support=box('s')
        m=model(panel,support);m['validation']['rules']=[{'kind':'panel_support','parts':['p','s'],'bearing_width':.75}]
        findings=validate(m)
        self.assertTrue(any(f['status']=='UNVERIFIED' for f in findings))
        self.assertEqual(coverage(m,findings)['checked_parts'],0)

    def test_warning_rule_requires_explanation(self):
        m=model(box('a'),box('b'));m['validation']['rules']=[{'kind':'minimum_contact','parts':['a','b'],'minimum_area':1,'severity':'WARNING'}]
        self.assertTrue(any(f['status']=='FAIL' and f['rule']=='configuration' for f in validate(m)))
