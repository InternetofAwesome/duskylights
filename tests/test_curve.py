import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "custom_components" / "duskylights"))
import curve


class CurveTests(unittest.TestCase):
    def test_endpoints(self):
        for a in (0, 1, 3):
            for b in (0, 1, 3):
                self.assertAlmostEqual(curve.shape(0, a, b), 1.0)
                self.assertAlmostEqual(curve.shape(1, a, b), 0.0)

    def test_sharpness_one_is_a_straight_line(self):
        for i in range(11):
            x = i / 10
            self.assertAlmostEqual(curve.shape(x, 1, 1), 1 - x)

    def test_monotonic_over_full_range(self):
        for a in (0, 0.5, 1, 2, 3):
            for b in (0, 0.5, 1, 2, 3):
                prev = 1.0
                for i in range(1, 1001):
                    v = curve.shape(i / 1000, a, b)
                    self.assertLessEqual(v, prev + 1e-12, (a, b, i))
                    prev = v

    def test_end_slopes_match_sharpness(self):
        eps = 1e-6
        for a in (0, 1, 2.5):
            self.assertAlmostEqual((curve.shape(eps, a, 0) - 1) / eps, -a, places=3)
        for b in (0, 1, 2.5):
            self.assertAlmostEqual((0 - curve.shape(1 - eps, 0, b)) / eps, -b, places=3)

    def test_mid_slope_formula(self):
        eps = 1e-6
        for a, b in ((0, 0), (1, 1), (2, 3)):
            slope = (curve.shape(0.5 + eps, a, b) - curve.shape(0.5 - eps, a, b)) / (
                2 * eps
            )
            self.assertAlmostEqual(slope, -(1.5 - (a + b) / 4), places=4)

    def test_clamps(self):
        self.assertEqual(curve.shape(-1), 1.0)
        self.assertEqual(curve.shape(2), 0.0)
        self.assertAlmostEqual(curve.shape(0.3, 99, 99), curve.shape(0.3, 3, 3))

    def test_target_pct_window(self):
        kw = {"start": 10, "end": -6, "normal": 50, "floor": 10}
        self.assertEqual(curve.target_pct(30, **kw), 50)
        self.assertEqual(curve.target_pct(-20, **kw), 10)
        mid = curve.target_pct(2, **kw)  # halfway through the window
        self.assertAlmostEqual(mid, 30.0)

    def test_floor_above_normal_is_clamped(self):
        self.assertEqual(curve.target_pct(-20, 10, -6, normal=20, floor=40), 20)

    def test_degenerate_window_holds_normal(self):
        self.assertEqual(curve.target_pct(0, 5, 5, 50, 10), 50)

    def test_worst_step_with_interpolation_under_one_point(self):
        # Steepest default slope is 1.5 * 40 pts / 16 deg = 3.75 pts/deg; a
        # 15 s tick at 0.175 deg/min moves 0.044 deg = 0.16 pts.
        step = 3.75 * 0.175 / 60 * 15
        self.assertLess(step, 1.0)

    def test_interpolation(self):
        self.assertEqual(curve.interpolate_elevation(None, (100, 5.0), 160), 5.0)
        got = curve.interpolate_elevation((0, 6.0), (120, 5.0), 180)
        self.assertAlmostEqual(got, 5.0 - 0.5)  # 60 s at -1 deg / 120 s
        far = curve.interpolate_elevation((0, 6.0), (120, 5.0), 10_000)
        self.assertAlmostEqual(far, 5.0 - 2.0)  # capped at 2 segments
        self.assertEqual(curve.interpolate_elevation((0, 6.0), (120, 5.0), 100), 5.0)
        self.assertEqual(curve.interpolate_elevation((0, 6.0), (4000, 5.0), 4100), 5.0)
        # two readings a moment apart give no usable slope
        self.assertEqual(
            curve.interpolate_elevation((100.0, 30.0), (100.01, 2.0), 105), 2.0
        )
        self.assertFalse(math.isnan(far))


if __name__ == "__main__":
    unittest.main()
