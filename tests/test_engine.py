import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "custom_components" / "duskylights"))
from engine import Action, Engine, pct_to_bri


class Fixture(unittest.TestCase):
    def setUp(self):
        self.pct = {"a": 50.0, "b": 50.0}
        self.e = Engine(lambda light: self.pct[light])
        self.t = 0.0

    def tick(self, states, dawn=False, dt=60.0):
        self.t += dt
        return self.e.tick(states, now=self.t, dawn=dawn)

    def seen(self, light, brightness, was_on=True, is_on=True, dt=60.0):
        self.t += dt
        return self.e.observe(
            light, was_on=was_on, is_on=is_on, brightness=brightness, now=self.t
        )


class EngineTests(Fixture):
    def test_pct_to_bri(self):
        self.assertEqual(pct_to_bri(50), 128)
        self.assertEqual(pct_to_bri(0), 1)
        self.assertEqual(pct_to_bri(100), 255)

    def test_off_to_on_goes_to_target(self):
        acts = self.seen("a", 200, was_on=False)
        self.assertEqual(acts, [Action("a", 128)])

    def test_follows_target_down_in_steps(self):
        states = {"a": (True, 128)}
        self.assertEqual(self.tick(states), [])  # already at target
        self.pct["a"] = 40.0  # 102
        self.assertEqual(self.tick(states), [Action("a", 102)])
        # a change under ~1 % is not chased
        self.pct["a"] = 39.5
        self.assertEqual(self.tick({"a": (True, 102)}), [])

    def test_manual_dim_holds_then_sun_catches_down(self):
        self.seen("a", 60)  # user dims 128 -> 60
        self.assertEqual(self.e.holds["a"].level, 60)
        self.assertTrue(self.e.holds["a"].dimmed)
        self.assertEqual(self.tick({"a": (True, 60)}), [])  # held at target 128
        self.pct["a"] = 30.0  # 77 > 60: still held
        self.assertEqual(self.tick({"a": (True, 60)}), [])
        self.pct["a"] = 20.0  # 51 < 60: sun owns it again
        self.assertEqual(self.tick({"a": (True, 60)}), [Action("a", 51)])
        self.assertNotIn("a", self.e.holds)

    def test_manual_raise_holds_through_dusk(self):
        self.pct["a"] = 30.0  # target 77
        self.seen("a", 200)  # user raises
        self.assertFalse(self.e.holds["a"].dimmed)
        self.pct["a"] = 10.0
        self.assertEqual(self.tick({"a": (True, 200)}), [])
        self.assertIn("a", self.e.holds)

    def test_dawn_clears_holds_once(self):
        self.seen("a", 60)
        self.assertEqual(self.tick({"a": (True, 60)}, dawn=True), [Action("a", 128)])
        self.assertEqual(self.e.holds, {})
        self.seen("a", 60)  # user dims during dawn: stays held (no new edge)
        self.assertEqual(self.tick({"a": (True, 60)}, dawn=True), [])
        self.assertIn("a", self.e.holds)

    def test_off_then_on_resets_hold(self):
        self.seen("a", 60)
        self.seen("a", None, was_on=True, is_on=False)
        self.assertEqual(self.e.holds, {})
        self.assertEqual(self.seen("a", 60, was_on=False), [Action("a", 128)])

    def test_own_ramp_reports_are_not_manual(self):
        self.tick({"a": (True, 60)})  # nothing held, so we command 128
        self.assertIn("a", self.e._last_set)
        # intermediate reports during the dimmer's own ramp, inside the settle window
        self.assertEqual(self.seen("a", 90, dt=1.0), [])
        self.assertEqual(self.e.holds, {})
        # a final report close to what we asked, after the window
        self.assertEqual(self.seen("a", 126, dt=10.0), [])
        self.assertEqual(self.e.holds, {})

    def test_landing_on_the_curve_clears_hold(self):
        self.seen("a", 60)
        self.assertIn("a", self.e.holds)
        self.seen("a", 128)
        self.assertNotIn("a", self.e.holds)

    def test_release_returns_light_to_curve(self):
        self.seen("a", 60)
        self.e.release("a")
        self.assertEqual(self.tick({"a": (True, 60)}), [Action("a", 128)])

    def test_release_is_per_light(self):
        self.seen("a", 60)
        self.seen("b", 60)
        self.e.release("a")
        self.assertNotIn("a", self.e.holds)
        self.assertIn("b", self.e.holds)

    def test_adopt_marks_away_from_target_as_manual(self):
        self.e.adopt("a", True, 60)
        self.assertTrue(self.e.holds["a"].dimmed)
        self.e.adopt("b", True, 130)  # within tolerance of 128
        self.assertNotIn("b", self.e.holds)
        self.e.adopt("b", False, None)

    def test_rooms_are_independent(self):
        self.pct["b"] = 20.0
        acts = self.tick({"a": (True, 128), "b": (True, 128)})
        self.assertEqual(acts, [Action("b", 51)])

    def test_off_light_is_never_commanded(self):
        self.assertEqual(self.tick({"a": (False, None)}), [])

    def test_continuous_ramp_never_triggers_manual(self):
        """Many small own steps, each reported back, must never look manual."""
        bri = 128
        states = {"a": (True, bri)}
        for step in range(40):
            self.pct["a"] = 50.0 - step * 0.5
            for act in self.tick(states, dt=15.0):
                bri = act.brightness
                states = {"a": (True, bri)}
                self.seen("a", bri, dt=2.0)
        self.assertEqual(self.e.holds, {})


if __name__ == "__main__":
    unittest.main()
