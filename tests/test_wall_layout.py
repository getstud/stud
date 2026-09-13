import unittest
from dataclasses import replace
from stud.wall_layout import WallLine, WallRun, WallOpening, layout_walls


def wall(id, a, b, **kw):
    return WallRun(id, WallLine(id, a, b, 0), 96, 3.5, **kw)


class WallLayoutTests(unittest.TestCase):
    def test_named_faces_follow_changed_edge(self):
        a = wall('a', (0, 0), (120, 0))
        b = replace(a, depth=5.5)
        self.assertEqual(a.face('inside').start, (0, 3.5))
        self.assertEqual(b.face('inside').start, (0, 5.5))
        self.assertEqual(replace(a, alignment='center').outside.start, (0, -1.75))

    def test_mixed_depth_t_and_corner_are_order_independent(self):
        a = replace(wall('outside', (0, 0), (120, 0)), depth=5.5)
        b = wall('return', (120, 0), (120, 80))
        c = wall('partition', (60, 0), (60, 80))
        result = layout_walls([a, b, c])
        self.assertEqual(result, layout_walls([c, b, a]))
        self.assertTrue(all(w.neighbors for w in result.walls))
        self.assertTrue(any(w.lower != w.upper for w in result.walls))

    def test_fixed_opening_conflict_is_explicit_and_movement_is_bounded(self):
        a = wall('a', (0, 0), (120, 0), openings=(WallOpening('door', -1, 32, 82),))
        with self.assertRaisesRegex(ValueError, 'fixed opening'):
            layout_walls([a])
        opening = replace(a.openings[0], max_shift=4)
        result = layout_walls([replace(a, openings=(opening,))])
        self.assertEqual(result.adjustments, (('a', 'door', 4),))
        with self.assertRaises(ValueError):
            layout_walls([replace(a, openings=(replace(opening, max_shift=3),))])

    def test_duplicate_shared_wall_is_rejected(self):
        a = wall('a', (0, 0), (120, 0))
        with self.assertRaisesRegex(ValueError, 'author the wall once'):
            layout_walls([a, replace(a, id='b')])

    def test_tall_wall_does_not_steal_short_wall_upper_plate(self):
        a = wall('a', (0, 0), (120, 0))
        b = replace(wall('b', (120, 0), (120, 80)), height=144)
        result = layout_walls([a, b])
        self.assertTrue(all(w.lower == w.upper for w in result.walls))

    def test_unrelated_wall_does_not_change_local_resolution(self):
        a = wall('a', (0, 0), (120, 0))
        b = wall('b', (300, 0), (420, 0))
        self.assertEqual(layout_walls([a]).walls[0], layout_walls([a, b]).walls[0])

    def test_collinear_and_angled_runs(self):
        for end in ((240, 0), (180, 60)):
            with self.subTest(end=end):
                result = layout_walls([wall('a', (0, 0), (120, 0)), wall('b', (120, 0), end)])
                self.assertEqual(len(result.walls), 2)
                self.assertEqual(result.walls[0].neighbors, ('b',))
