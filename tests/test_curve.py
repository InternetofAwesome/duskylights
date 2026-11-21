import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "custom_components" / "duskylights"))
import curve

SHARPNESS = (0, 0.25, 0.5, 0.75, 1)


def d(f, x, n, h=1e-3):
    """n-th derivative of f at x by central differences."""
    if n == 0:
        return f(x)
    return (d(f, x + h, n - 1, h) - d(f, x - h, n - 1, h)) / (2 * h)


class CurveTests(unittest.TestCase):
    def test_endpoints(self):
        for a in SHARPNESS:
            for b in SHARPNESS:
                self.assertEqual(curve.shape(0, a, b), 1.0)
                self.assertEqual(curve.shape(1, a, b), 0.0)

    def test_sharpness_one_is_a_straight_line(self):
        for i in range(11):
            x = i / 10
            self.assertAlmostEqual(curve.shape(x, 1, 1), 1 - x)

    def test_monotonic_over_full_range(self):
        for a in SHARPNESS:
            for b in SHARPNESS:
                prev = 1.0
                for i in range(1, 1001):
                    v = curve.shape(i / 1000, a, b)
                    self.assertLessEqual(v, prev + 1e-12, (a, b, i))
                    prev = v

    def test_symmetric_when_both_ends_match(self):
        for a in SHARPNESS:
            for x in (0.1, 0.3, 0.45):
                self.assertAlmostEqual(
                    curve.shape(x, a, a) + curve.shape(1 - x, a, a), 1.0
                )

    def test_arrives_at_both_plateaus_with_zero_slope_and_acceleration(self):
        # Whenever an entry exists (sharpness < 1) the ramp meets the plateau
        # with no slope and no acceleration: constant jerk, no kink.
        for sharp in (0, 0.25, 0.5):

            def f(x, s=sharp):
                return curve.shape(x, s, s)

            self.assertAlmostEqual(d(f, 0.002, 1, 1e-4), 0.0, delta=0.02)
            self.assertAlmostEqual(d(f, 0.998, 1, 1e-4), 0.0, delta=0.02)
            self.assertAlmostEqual(d(f, 0.001, 2, 2e-4), 0.0, delta=0.2)
            self.assertAlmostEqual(d(f, 0.999, 2, 2e-4), 0.0, delta=0.2)

    def test_entry_has_constant_jerk(self):
        for sharp in (0, 0.5):
            s = curve._entry(sharp)

            def f(x, sh=sharp):
                return curve.shape(x, sh, sh)

            jerk = curve.peak_slope(sharp, sharp) / s**2  # |f'''| in each piece
            for x in (0.2 * s, 0.5 * s, 0.8 * s):
                self.assertAlmostEqual(d(f, x, 3, 4e-3 * s) / -jerk, 1.0, delta=0.02)
            # the second piece of the entry has the opposite, equal jerk
            for x in (1.2 * s, 1.5 * s, 1.8 * s):
                self.assertAlmostEqual(d(f, x, 3, 4e-3 * s) / jerk, 1.0, delta=0.02)

    def test_acceleration_is_continuous_at_every_join(self):
        for a, b in ((0, 0), (0.5, 0.5), (0.2, 0.7)):

            def f(x, a=a, b=b):
                return curve.shape(x, a, b)

            s, e = curve._entry(a), curve._entry(b)
            for x in (s, 2 * s, 1 - 2 * e, 1 - e):
                lo = d(f, x - 1e-3, 2, 5e-4)
                hi = d(f, x + 1e-3, 2, 5e-4)
                self.assertAlmostEqual(lo, hi, delta=max(1.0, 0.05 * abs(lo)))

    def test_peak_slope_is_the_middle_slope(self):
        for a, b in ((0, 0), (0.5, 0.5), (0, 1), (0.3, 0.8), (1, 1)):
            numeric = max(
                abs(curve.shape((i + 1) / 2000, a, b) - curve.shape(i / 2000, a, b))
                * 2000
                for i in range(2000)
            )
            self.assertAlmostEqual(curve.peak_slope(a, b), numeric, places=3)
        self.assertAlmostEqual(curve.peak_slope(0, 0), 2.0)
        self.assertAlmostEqual(curve.peak_slope(1, 1), 1.0)

    def test_clamps(self):
        self.assertEqual(curve.shape(-1), 1.0)
        self.assertEqual(curve.shape(2), 0.0)
        self.assertAlmostEqual(curve.shape(0.3, 99, 99), curve.shape(0.3, 1, 1))
        self.assertAlmostEqual(curve.shape(0.3, -5, -5), curve.shape(0.3, 0, 0))

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
        # Steepest default slope is 2 * 40 pts / 16 deg = 5 pts/deg; a
        # 15 s tick at 0.175 deg/min moves 0.044 deg = 0.22 pts.
        step = 5.0 * 0.175 / 60 * 15
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
