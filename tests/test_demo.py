import dataclasses
import sys
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parents[1] / "custom_components"))
from duskylights import curve, demo, engine, solar

LAT, LON = 37.7793, -122.4193  # San Francisco City Hall (public landmark)
# 2026-11-20 12:00 local (PST = UTC-8)
NOON = datetime(2026, 11, 20, 20, 0, tzinfo=UTC)


def make(duration_s, loop=False, start=NOON):
    return demo.Demo(LAT, LON, start, 0.0, duration_s, loop)


class SolarTests(unittest.TestCase):
    def test_noon_and_midnight(self):
        self.assertAlmostEqual(solar.elevation(LAT, LON, NOON), 32.6, delta=0.7)
        self.assertLess(solar.elevation(LAT, LON, NOON + timedelta(hours=12)), -40)


class DemoTests(unittest.TestCase):
    def test_speed_and_progress(self):
        d = make(600)
        self.assertAlmostEqual(d.speed, 144.0)
        self.assertEqual(d.progress(0), 0.0)
        self.assertAlmostEqual(d.progress(300), 0.5)
        self.assertIsNone(d.progress(600))
        self.assertIsNone(d.elevation(601))

    def test_loop_wraps(self):
        d = make(600, loop=True)
        self.assertAlmostEqual(d.progress(750), 0.25)
        self.assertIsNotNone(d.elevation(5000))

    def test_virtual_time_runs_through_a_day(self):
        d = make(600)
        self.assertEqual(d.virtual_time(0), NOON)
        self.assertEqual(d.virtual_time(300), NOON + timedelta(hours=12))

    def test_rising_flag(self):
        d = make(600)
        self.assertFalse(d.rising(0))  # noon onwards: falling
        self.assertFalse(d.rising(100))  # ~16:00
        self.assertTrue(d.rising(500))  # ~08:00 next morning

    def test_tick_interval_clamps(self):
        self.assertEqual(make(86400).tick_interval(), 15.0)  # real time
        self.assertAlmostEqual(make(600).tick_interval(), 120 / 144)
        self.assertEqual(make(20).tick_interval(), 0.25)  # absurdly fast


class SeasonTests(unittest.TestCase):
    """The demo follows the real sun for the chosen date, not a generic day."""

    def day(self, d, hour):
        return demo.Demo.for_day(
            lat=LAT,
            lon=LON,
            tz=ZoneInfo("America/Los_Angeles"),
            day=d,
            start_hour=hour,
            started_at=0.0,
            duration_s=600,
        )

    def test_start_is_local_time_on_that_date(self):
        d = self.day(date(2026, 11, 20), 12)
        self.assertEqual(d.virtual_start, NOON)  # 12:00 PST
        self.assertEqual(self.day(date(2026, 6, 21), 12).virtual_start.hour, 12)

    def test_summer_and_winter_differ(self):
        winter, summer = (
            self.day(date(2026, 11, 20), 12),
            self.day(date(2026, 6, 21), 12),
        )
        self.assertLess(winter.elevation(0), 40)
        self.assertGreater(summer.elevation(0), 60)
        # 19:00 local is 7/24 of the way through the day (progress 7/24):
        t = 600 * 7 / 24
        self.assertLess(winter.elevation(t), -10)  # long dark already
        self.assertGreater(summer.elevation(t), 5)  # still daylight


class FullDaySimulation(unittest.TestCase):
    """Curve + engine + demo against an instantly-obeying fake light."""

    def run_demo(self, duration_s):
        d = make(duration_s)
        e = engine.Engine(
            lambda _light: curve.target_pct(
                self.elev, start=10, end=-6, normal=50, floor=10
            )
        )
        bri = 128
        e.observe("l", was_on=False, is_on=True, brightness=bri, now=0.0)
        t, step, log = 0.0, d.tick_interval(), []
        prev_bri = bri
        while True:
            elev = d.elevation(t)
            if elev is None:
                break
            self.elev = elev
            for act in e.tick({"l": (True, bri)}, now=t, dawn=self._dawn(d, t, elev)):
                bri = act.brightness
                e.observe("l", was_on=True, is_on=True, brightness=bri, now=t + 0.1)
            log.append((d.virtual_time(t), elev, bri, abs(bri - prev_bri)))
            prev_bri = bri
            t += step
        return log, e

    @staticmethod
    def _dawn(d, t, elev):
        return d.rising(t) and -6 <= elev < 10

    def test_full_day(self):
        self.elev = 30.0
        log, e = self.run_demo(600)
        by_hour = {}
        for vt, _elev, bri, _ in log:
            by_hour.setdefault(vt.astimezone(UTC).hour, bri)
        # virtual 12:00 local = 20 UTC. Noon: normal. Late evening/night: floor.
        self.assertEqual(by_hour[20], 128)
        self.assertEqual(by_hour[(20 + 8) % 24], 26)  # 04:00 local, pitch dark
        self.assertEqual(by_hour[(20 + 22) % 24], 128)  # next-day 10:00 local
        self.assertEqual(e.holds, {})  # nothing it did looked manual
        # No step bigger than ~2.5 %: the point of interpolating/ticking finely.
        self.assertLessEqual(max(s for *_, s in log), 7)

    def test_dusk_is_monotonic_down_and_dawn_up(self):
        self.elev = 30.0
        log, _ = self.run_demo(600)
        dusk = [b for vt, el, b, _ in log if vt < NOON + timedelta(hours=8)]
        dawn = [b for vt, el, b, _ in log if vt > NOON + timedelta(hours=16)]
        self.assertEqual(dusk, sorted(dusk, reverse=True))
        self.assertEqual(dawn, sorted(dawn))


if __name__ == "__main__":
    unittest.main()


class CycleTests(unittest.TestCase):
    TZ = ZoneInfo("America/Los_Angeles")

    def make_cycle(self, ramp_s, **kw):
        return demo.Demo.cycle(
            lat=LAT,
            lon=LON,
            tz=self.TZ,
            day=date(2026, 11, 20),
            start_hour=12,
            started_at=0.0,
            start_elev=10.0,
            end_elev=-6.0,
            ramp_s=ramp_s,
            **kw,
        )

    def test_length_is_two_ramps_and_three_holds(self):
        d = self.make_cycle(15.0)
        self.assertAlmostEqual(d.duration_s, 2 * 15.0 + 3 * demo.HOLD_S)
        self.assertIsNone(d.virtual_time(d.duration_s + 0.1))

    def test_min_ramp_seconds(self):
        # 40 % swing, smoothstep peak slope 1.5, 0.25 s tick, 1 % steps -> 15 s
        self.assertAlmostEqual(
            demo.min_ramp_seconds(40.0, curve.peak_slope(0, 0)), 15.0, places=1
        )
        # sharper ends are steeper, so they need longer
        self.assertGreater(
            demo.min_ramp_seconds(40.0, curve.peak_slope(3, 3)),
            demo.min_ramp_seconds(40.0, curve.peak_slope(0, 0)),
        )

    def test_auto_cycle_never_steps_more_than_about_one_percent(self):
        ramp = demo.min_ramp_seconds(40.0, curve.peak_slope(0, 0))
        d = self.make_cycle(ramp)
        prev = None
        worst = 0.0
        t = 0.0
        while t < d.duration_s:
            e = d.elevation(t)
            pct = curve.target_pct(e, 10.0, -6.0, 50.0, 10.0)
            if prev is not None:
                worst = max(worst, abs(pct - prev))
            prev = pct
            t += d.tick_interval()
        self.assertLess(worst, 1.25)

    def test_cycle_plays_dusk_then_dawn(self):
        ramp = 15.0
        d = self.make_cycle(ramp)
        targets = []
        t = 0.0
        while t < d.duration_s:
            e = d.elevation(t)
            targets.append(curve.target_pct(e, 10.0, -6.0, 50.0, 10.0))
            t += 0.25
        self.assertAlmostEqual(targets[0], 50.0, places=1)  # noon: high
        self.assertAlmostEqual(min(targets), 10.0, places=1)  # night: low
        self.assertAlmostEqual(targets[-1], 50.0, places=1)  # next noon: high
        low_at = targets.index(min(targets))
        self.assertTrue(0 < low_at < len(targets) - 1)


class StartOffsetTests(unittest.TestCase):
    def setUp(self):
        self.d = CycleTests().make_cycle(15.0)
        self.pct = lambda e: curve.target_pct(e, 10.0, -6.0, 50.0, 10.0)

    def off(self, level):
        return self.d.start_offset(self.pct, level, 50.0, 10.0)

    def test_off_or_low_starts_the_dawn_ramp(self):
        dawn_start = self.d.keys[3][0]
        self.assertEqual(self.off(None), dawn_start)
        self.assertEqual(self.off(10.0), dawn_start)

    def test_high_starts_the_dusk_ramp_without_the_leading_hold(self):
        self.assertEqual(self.off(50.0), self.d.keys[1][0])

    def test_middle_level_starts_partway_down_the_dusk_ramp(self):
        t = self.off(30.0)
        self.assertTrue(self.d.keys[1][0] < t < self.d.keys[2][0])
        self.assertAlmostEqual(self.pct(self.d.elevation_at(t)), 30.0, delta=1.0)

    def test_one_shot_is_a_full_cycle_from_the_start_point(self):
        d = dataclasses.replace(self.d, start_offset_s=self.d.keys[3][0])
        self.assertIsNotNone(d.elevation(d.duration_s - 0.1))
        self.assertIsNone(d.elevation(d.duration_s + 0.1))
        # starts low (dawn ramp), passes through high, ends back at low
        self.assertAlmostEqual(self.pct(d.elevation(0.0)), 10.0, delta=1.0)
        self.assertAlmostEqual(
            self.pct(d.elevation(d.duration_s - 0.1)), 10.0, delta=1.5
        )
        peak = max(
            self.pct(d.elevation(t * 0.25)) for t in range(int(d.duration_s * 4))
        )
        self.assertAlmostEqual(peak, 50.0, delta=1.0)
