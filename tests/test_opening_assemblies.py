import copy
from pathlib import Path
import unittest

from build import compile_project
from stud import Project, WallFrame, framed_opening
from validate import validate
from validation_rules import coverage


ROOT = Path(__file__).resolve().parents[1]


def opening_project(**overrides):
    project = Project('Opening fixture')
    project.stock('stud', 'Stud', '#aaa', section=(1.5, 3.5), lengths=(96, 120, 144))
    project.stock('header', 'Header', '#bbb', section=(1.5, 7.25), lengths=(96, 120))
    project.stock('spacer', 'Spacer', '#ccc', sheet=(48, 96))
    parameters = dict(frame=WallFrame(), start=24, width=36, bottom=40, height=36,
                      wall_height=96, stud_stock='stud', header_stock='header',
                      spacer_stock='spacer', field_studs=[('field.1', 32), ('field.2', 48)])
    parameters.update(overrides)
    opening = framed_opening(project, 'window.a', **parameters)
    return project, opening


class OpeningAssemblyTests(unittest.TestCase):
    def assert_passes(self, project):
        model = project.export()
        findings = validate(model)
        self.assertTrue(findings)
        self.assertEqual({f['status'] for f in findings}, {'PASS'}, findings)
        self.assertEqual(len(coverage(model, findings)['requirements']), 5)
        return findings

    def test_resized_rotated_and_mirrored_assemblies(self):
        for width, bottom, height in [(24, 0, 80), (36, 40, 36), (60, 24, 48)]:
            for angle in (0, 90, 180, 270, 37):
                for inward in (-1, 1):
                    with self.subTest(width=width, angle=angle, inward=inward, bottom=bottom):
                        project, opening = opening_project(
                            width=width, bottom=bottom, height=height, field_studs=[],
                            frame=WallFrame((103, -41, 7.75), angle, inward))
                        findings = self.assert_passes(project)
                        bearing = [f for f in findings if f['rule']=='minimum_contact']
                        self.assertEqual(len(bearing), 4)
                        for finding in bearing:
                            self.assertAlmostEqual(finding['measured']['contact_area_sq_in'], 2.25)
                            self.assertEqual(finding['source']['component'], opening.id)

    def test_missing_and_shortened_jack_fail_its_bearing_requirements(self):
        for remove in (False, True):
            with self.subTest(remove=remove):
                project, opening = opening_project(frame=WallFrame((12, 34, 7.75), 37, -1))
                jack = next(p for p in project.parts if p['id']==opening.roles['jack.left'])
                if remove:
                    project.parts.remove(jack)
                else:
                    jack['size'][2] -= .25
                    jack['cut_length'] -= .25
                findings = validate(project.export())
                for ply in (0, 1):
                    failure = next(f for f in findings if f.get('rule_id')==f'window.a.bearing.{ply}.left')
                    self.assertEqual(failure['status'], 'FAIL')

    def test_late_scope_member_obstructs_rotated_opening(self):
        project, opening = opening_project(frame=WallFrame((25, -30, 10), 37, -1))
        project.box('late.block', 'Host wall', 'stud',
                    **opening.frame.box((30, 0, 44), (1.5, 3.5, 10)))
        opening.include_in_clearance([project.parts[-1]])
        failures = [f for f in validate(project.export())
                    if f['status']=='FAIL' and f['rule']=='opening_clearance']
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]['parts'], ['late.block'])
        self.assertEqual(failures[0]['rule_id'], 'window.a.clearance')

    def test_scopes_do_not_capture_intentional_window_unit(self):
        project, opening = opening_project()
        project.box('window.unit', 'Window product', 'stud', (1.5, 3.5, 20), (32, 0, 44))
        self.assert_passes(project)

    def test_cripples_and_sill_follow_dimensions(self):
        project, opening = opening_project()
        self.assert_passes(project)
        parts = {p['id']:p for p in project.parts}
        self.assertEqual(parts['field.1.lower']['size'][2], 37)
        self.assertEqual(parts['field.1.upper']['origin'][2], 83.25)
        self.assertEqual(parts['field.1.upper']['size'][2], 9.75)
        self.assertEqual(parts[opening.roles['sill']]['origin'][2], 38.5)

    def test_thicker_wall_derives_spacer_and_bearing_from_stock(self):
        project, _ = opening_project()
        project.stock('deep', '2x6', '#aaa', section=(1.5, 5.5), lengths=(96, 120))
        framed_opening(project, 'window.b', frame=WallFrame((200, 0, 0)), start=24,
                       width=36, bottom=24, height=48, wall_height=96,
                       stud_stock='deep', header_stock='header', spacer_stock='spacer')
        findings=validate(project.export())
        self.assertEqual({f['status'] for f in findings}, {'PASS'}, findings)
        spacer = next(p for p in project.parts if p['id']=='window.b.header.spacer')
        self.assertEqual(spacer['size'][1], 2.5)

    def test_removed_rule_is_unverified_despite_automatic_checks(self):
        project, _ = opening_project()
        project.validation['rules'] = [r for r in project.validation['rules']
                                       if r['id']!='window.a.bearing.0.left']
        model = project.export()
        findings = validate(model)
        requirement = next(r for r in coverage(model, findings)['requirements']
                           if r['id']=='window.a.bearing.0.left')
        self.assertEqual(requirement['status'], 'UNVERIFIED')
        self.assertTrue(any(f['rule']=='requirement' and f['status']=='UNVERIFIED' for f in findings))

    def test_reordering_rules_preserves_identity(self):
        project, _ = opening_project()
        before = {f['rule_id'] for f in validate(project.export()) if 'source' in f}
        project.validation['rules'].reverse()
        after = {f['rule_id'] for f in validate(project.export()) if 'source' in f}
        self.assertEqual(before, after)

    def test_automatic_check_cannot_satisfy_deleted_explicit_rule(self):
        project, _ = opening_project()
        project.validation['automatic'] = ['stock_fit']
        project.validation['requirements'][0]['rule_id'] = 'rule-0'
        findings = validate(project.export())
        self.assertTrue(any(f.get('rule_id')=='rule-0' and f['status']=='PASS' for f in findings))
        self.assertEqual(coverage(project.export(), findings)['requirements'][0]['status'], 'UNVERIFIED')

    def test_duplicate_rule_id_fails_instead_of_passing_requirement(self):
        project, _ = opening_project()
        project.validation['rules'].append(copy.deepcopy(project.validation['rules'][0]))
        model = project.export()
        findings = validate(model)
        self.assertTrue(any(f['status']=='FAIL' and 'Duplicate rule ID' in f['message'] for f in findings))
        self.assertEqual(coverage(model, findings)['requirements'][0]['status'], 'FAIL')

    def test_invalid_builder_inputs_do_not_mutate_project(self):
        project, _ = opening_project()
        before = copy.deepcopy(project.export())
        for changes in ({'height': 90}, {'spacer_stock': None}, {'width': float('nan')},
                        {'field_studs': [('field.bad', 23)]}):
            parameters = dict(frame=WallFrame(), start=24, width=36, bottom=40,
                              height=36, wall_height=96, stud_stock='stud',
                              header_stock='header', spacer_stock='spacer')
            parameters.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                framed_opening(project, 'new', **parameters)
            self.assertEqual(project.export(), before)

    def test_malformed_requirement_is_configuration_failure(self):
        project, _ = opening_project()
        project.validation['requirements'][0].pop('rule_id')
        findings = validate(project.export())
        self.assertEqual(findings[0]['status'], 'FAIL')
        coverage(project.export(), findings)

    def test_legacy_checks_also_satisfy_named_requirements(self):
        project, opening = opening_project()
        project.validation['rules'].append(dict(id='sill.level', kind='level_top',
                                               parts=[opening.roles['sill']],
                                               source={'component': opening.id}))
        project.validation['requirements'].append(dict(id='sill.level', rule_id='sill.level',
                                                      component=opening.id, label='Level sill'))
        model = project.export()
        findings = validate(model)
        self.assertEqual(coverage(model, findings)['requirements'][-1]['status'], 'PASS')
        finding = next(f for f in findings if f.get('rule_id')=='sill.level')
        self.assertEqual(finding['source']['component'], opening.id)
