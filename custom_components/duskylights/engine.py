"""Hold / release / apply logic for Dusky Lights. No Home Assistant imports.

The Home Assistant glue feeds this engine observations (a light changed, time
passed) and executes the `Action`s it returns, so every rule can be tested with
a fake clock.

Rules (per light):
  * Off -> on: any hold is cleared and the light goes to the current target.
  * On -> off: hold and bookkeeping cleared.
  * A brightness change we did not cause is manual and becomes a hold:
      - dimmed (below target): kept until the sun's target falls below it, then
        the sun owns the light again and it follows the curve down;
      - raised (above target): kept until off/on, dawn, or a release.
  * When the dawn ramp begins, every hold is cleared so lights rise with the sun.
  * `release` clears one light's hold; it returns to the curve at the next tick.
Brightness is 0-255 like Home Assistant's `brightness` attribute.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

SETTLE_S = 5.0  # ignore reports this long after our own command (ramps, echo)
TOLERANCE = 5  # /255; a report within this of what we asked is "ours"
APPLY_DELTA = 3  # /255 (~1 %); don't chase differences smaller than this


@dataclass(frozen=True)
class Action:
    """Ask the glue to set `light` to `brightness` (0-255)."""

    light: str
    brightness: int


@dataclass
class _Hold:
    level: int
    dimmed: bool


def pct_to_bri(pct: float) -> int:
    return max(1, min(255, round(pct * 255 / 100)))


class Engine:
    def __init__(self, target_pct: Callable[[str], float]) -> None:
        """`target_pct(light)` returns the curve's brightness percent now."""
        self._target_pct = target_pct
        self.holds: dict[str, _Hold] = {}
        self._last_set: dict[str, tuple[int, float]] = {}  # light -> (bri, time)
        self._was_dawn = False

    # ---- helpers -------------------------------------------------------
    def target(self, light: str) -> int:
        return pct_to_bri(self._target_pct(light))

    def _set(self, light: str, bri: int, now: float) -> Action:
        bri = max(1, min(255, bri))
        self._last_set[light] = (bri, now)
        return Action(light, bri)

    # ---- observations --------------------------------------------------
    def adopt(self, light: str, on: bool, brightness: int | None) -> None:
        """Start-up: a light already on and away from target counts as manual."""
        if not on or brightness is None:
            return
        target = self.target(light)
        if abs(brightness - target) > TOLERANCE:
            self.holds[light] = _Hold(brightness, brightness < target)

    def observe(
        self,
        light: str,
        *,
        was_on: bool,
        is_on: bool,
        brightness: int | None,
        now: float,
    ) -> list[Action]:
        """A light's state changed."""
        if not is_on:
            self.holds.pop(light, None)
            self._last_set.pop(light, None)
            return []
        if not was_on:  # off -> on: start fresh at the target
            self.holds.pop(light, None)
            self._last_set.pop(light, None)
            return [self._set(light, self.target(light), now)]
        if brightness is None:
            return []
        ours = self._last_set.get(light)
        if ours is not None and (
            now - ours[1] < SETTLE_S or abs(brightness - ours[0]) <= TOLERANCE
        ):
            return []
        target = self.target(light)
        if abs(brightness - target) <= TOLERANCE:  # landed on the curve
            self.holds.pop(light, None)
        else:
            self.holds[light] = _Hold(brightness, brightness < target)
        self._last_set[light] = (brightness, float("-inf"))  # now "ours"
        return []

    def release(self, light: str) -> None:
        self.holds.pop(light, None)
        self._last_set.pop(light, None)

    # ---- time ----------------------------------------------------------
    def tick(
        self,
        states: dict[str, tuple[bool, int | None]],
        *,
        now: float,
        dawn: bool,
    ) -> list[Action]:
        """Advance. `states` maps light -> (is_on, brightness)."""
        if dawn and not self._was_dawn:
            self.holds.clear()
        self._was_dawn = dawn

        actions: list[Action] = []
        for light, (is_on, current) in states.items():
            if not is_on:
                continue
            target = self.target(light)
            hold = self.holds.get(light)
            if hold and hold.dimmed and target < hold.level:
                del self.holds[light]  # the sun has caught down to the hold
                hold = None
            if hold:
                continue
            if current is not None and abs(current - target) < APPLY_DELTA:
                continue
            actions.append(self._set(light, target, now))
        return actions
