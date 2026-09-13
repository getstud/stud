import unittest
from dataclasses import replace
import cadquery as cq
from stud.cad import Model
from stud.checks import check_model
from stud.design_review import design_review
from stud.wall_layout import WallLine, WallRun, WallOpening, layout_walls
from stud.walls import HeaderDetail, OpeningDetail, PocketDetail, TransomDetail, frame_walls, plan_wall_members

HEADER = HeaderDetail(9.25)
OPENING = OpeningDetail(HEADER)


def run(openings=(), **kw):
    return WallRun('south', WallLine('deck.south', (0, 0), (120, 0), 1), 96, 5.5, openings=openings, **kw)


def fixture(w=None):
    model = Model('Generic wall detail', units='in')
    model.part('floor', cq.Workplane('XY').box(120, 80, 1, centered=(False, False, False)))
    model.requirement('floor.valid', 'solid_valid', ['floor'])
    result = frame_walls(model, [w or run()], floor_supports=['floor'])
    return model, result


class WallsTests(unittest.TestCase):
    def assert_checked(self, model):
        checks = check_model(model)
        self.assertTrue(checks['all_passed'], [f for f in checks['findings'] if f['status'] != 'passed'])

    def test_simple_wall_and_header_have_actual_bearing(self):
        for openings in ((), (WallOpening('door', 40, 32, 80, detail=OPENING),)):
            model, result = fixture(run(openings));self.assert_checked(model)
            self.assertTrue(result['plan'].members)

    def test_moved_opening_retains_unrelated_station_ids(self):
        opening = WallOpening('door', 40, 32, 80, detail=OPENING)
        a = plan_wall_members(layout_walls([run((opening,))]))
        b = plan_wall_members(layout_walls([run((replace(opening, station=48),))]))
        left = {m.id: m for m in a.members if m.role == 'stud' and m.origin[0] < 32}
        right = {m.id: m for m in b.members if m.role == 'stud' and m.origin[0] < 32}
        self.assertTrue(left);self.assertEqual(left, right)
        self.assertNotEqual(a.members, b.members)

    def test_removed_jack_cannot_disappear_from_inventory(self):
        model, result = fixture(run((WallOpening('door', 40, 32, 80, detail=OPENING),)))
        part = result['members']['south.jack.door.left']
        del model.objects[part];del model.shapes[part]
        for key in [key for key, r in model.requirements.items() if part in r['targets']]:del model.requirements[key]
        report = design_review(model.export())
        self.assertTrue(any(f['category'] == 'missing_parts' for f in report['findings']))
        self.assertTrue(any(f['category'] == 'missing_requirements' for f in report['findings']))

    def test_partial_floor_contact_fails_required_area(self):
        model, result = fixture()
        model.part('floor', cq.Workplane('XY').box(120, 3, 1, centered=(False, False, False)), replace=True)
        failures = [f for f in check_model(model)['findings'] if f['status'] == 'failed']
        self.assertTrue(any('plate.bottom' in f['requirement_id'] for f in failures))

    def test_header_plies_and_pocket_are_distinct_stock(self):
        pocket = PocketDetail(32, 1.5, 1.5, 'test-pocket')
        model, result = fixture(run((WallOpening('door', 20, 65, 80, detail=OpeningDetail(HEADER, pocket=pocket)),)))
        self.assert_checked(model)
        plies = [m for m in result['plan'].members if m.role == 'header']
        self.assertEqual(len(plies), 2)
        self.assertEqual([m.origin[1] for m in plies], [0, 4])
        self.assertEqual(len([m for m in result['plan'].members if m.role == 'pocket_stud']), 4)

    def test_stacked_opening_rail_derives_upper_sill(self):
        rail = TransomDetail(84, HeaderDetail(9.25, cap=0), 1.5)
        w = replace(run((WallOpening('stack', 20, 77, 142.75, detail=OpeningDetail(HEADER, transom=rail)),)), height=158.5)
        model, result = fixture(w);self.assert_checked(model)
        sill = next(m for m in result['plan'].members if m.id.endswith('fixed_sill'))
        self.assertEqual(sill.origin[2], 93.25)

    def test_invalid_header_rejected_before_model_mutation(self):
        model = Model('test', units='in')
        w = run((WallOpening('door', 40, 32, 80, detail=OpeningDetail(HeaderDetail(20))),))
        with self.assertRaisesRegex(ValueError, 'do not fit'):frame_walls(model, [w])
        self.assertFalse(model.objects);self.assertFalse(model.assemblies)

    def test_support_union_cannot_double_count_overlapping_hosts(self):
        model = Model('test', units='in')
        for pid in ('a', 'b'):
            model.part(pid, cq.Workplane('XY').box(4, 4, 1, centered=(False, False, False)))
        model.part('top', cq.Workplane('XY').box(8, 4, 1, centered=(False, False, False)).translate((0, 0, 1)))
        model.requirement('bearing', 'support', ['top', 'a', 'b'], threshold=32)
        finding = next(f for f in check_model(model)['findings'] if f['requirement_id'] == 'bearing')
        self.assertEqual(finding['status'], 'failed');self.assertAlmostEqual(finding['measured'], 16)

    def test_long_wall_splices_share_a_stud_seat(self):
        w = replace(run(), line=WallLine('edge', (0, 0), (300, 0), 1))
        model = Model('Long wall', units='in')
        model.part('floor', cq.Workplane('XY').box(300, 5.5, 1, centered=(False, False, False)))
        model.requirement('floor.valid', 'solid_valid', ['floor'])
        frame_walls(model, [w], floor_supports=['floor']);self.assert_checked(model)

    def test_cap_bearing_follows_single_and_narrow_plies(self):
        for header in (HeaderDetail(9.25, plies=1), HeaderDetail(9.25, ply_width=1)):
            model, _ = fixture(run((WallOpening('door', 40, 32, 80, detail=OpeningDetail(header)),)))
            self.assert_checked(model)

    def test_pocket_base_and_studs_can_have_different_sections(self):
        pocket = PocketDetail(32, 2.5, 1.5, 'pocket-stock')
        model, result = fixture(run((WallOpening('door', 20, 65, 80, detail=OpeningDetail(HEADER, pocket=pocket)),)))
        self.assert_checked(model)
        materials = {o['material'] for o in model.objects.values()}
        self.assertTrue({'pocket-stock.base', 'pocket-stock.stud'} <= materials)

    def test_caller_mutation_cannot_move_an_existing_plan(self):
        a, b = [0, 0], [120, 0];openings = []
        w = WallRun('south', WallLine('edge', a, b, 1), 96, 5.5, openings=openings)
        plan = plan_wall_members(layout_walls([w]));a[0] = 1000;b[0] = 2000
        openings.append(WallOpening('door', 40, 32, 80, detail=OPENING))
        self.assertEqual(plan.layout.walls[0].run.line.start, (0, 0))
        self.assertEqual(plan.layout.walls[0].openings, ())

    def test_complete_corner_and_t_framing(self):
        w = run()
        for a, b in (((120, 0), (120, 80)), ((60, 0), (60, 80))):
            other = WallRun('return', WallLine('edge2', a, b, 1), 96, 3.5)
            model = Model('Junction', units='in')
            model.part('floor', cq.Workplane('XY').box(125, 85, 1, centered=(False, False, False)))
            model.requirement('floor.valid', 'solid_valid', ['floor'])
            frame_walls(model, [w, other], floor_supports=['floor']);self.assert_checked(model)

    def test_angled_and_negative_ends_use_planned_seats_without_sliver_plates(self):
        cases = [
            [run(), WallRun('angled', WallLine('edge2', (120, 0), (180, 60), 1), 96, 5.5)],
            [replace(run(), footprint=((-5, 0), (120, 0), (125, 5.5), (0, 5.5)))],
        ]
        for walls in cases:
            model = Model('Angled junction', units='in')
            model.part('floor', cq.Workplane('XY').box(220, 120, 1, centered=(False, False, False)).translate((-10, -10, 0)))
            model.requirement('floor.valid', 'solid_valid', ['floor'])
            result = frame_walls(model, walls, floor_supports=['floor']);self.assert_checked(model)
            self.assertFalse(result['plan'].issues)
            for m in result['plan'].members:
                if m.role == 'plate_top1':self.assertGreater(m.length, 5)

    def test_custom_stock_limit_coordinates_splices_with_field_studs(self):
        from stud.walls import FramingDetail, PlateDetail
        w = replace(run(), line=WallLine('edge', (0, 0), (300, 0), 1))
        model = Model('Short plate stock', units='in')
        model.part('floor', cq.Workplane('XY').box(300, 10, 1, centered=(False, False, False)))
        model.requirement('floor.valid', 'solid_valid', ['floor'])
        result = frame_walls(model, [w], detail=FramingDetail(plates=PlateDetail(100, 50, 24)), floor_supports=['floor'])
        self.assert_checked(model)
        self.assertTrue(all(m.length <= 100 for m in result['plan'].members if m.role.startswith('plate_')))

    def test_uncapped_header_supports_cripples_on_selected_plies(self):
        model, result = fixture(run((WallOpening('door', 40, 32, 80, detail=OpeningDetail(HeaderDetail(9.25, cap=0))),)))
        self.assert_checked(model)
        self.assertTrue(any(m.role == 'cripple' and m.bearing_strips for m in result['plan'].members))
