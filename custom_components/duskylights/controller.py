"""Home Assistant side of Dusky Lights: listeners, timers and light commands.

All decisions live in `engine.py` and `curve.py`; this module feeds them real
states and carries out the actions they return.
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from typing import TYPE_CHECKING

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_TRANSITION
from homeassistant.const import ATTR_ENTITY_ID, STATE_ON
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.util import dt as dt_util

from . import curve
from .const import (
    DEFAULTS,
    GLOBAL_NUMBERS,
    K_END,
    K_FLOOR,
    K_NORMAL,
    K_SHARP_END,
    K_SHARP_START,
    K_START,
    TICK_S,
    TRANSITION_S,
    TURN_ON_DELAY_S,
)
from .demo import HOLD_S, Demo, min_ramp_seconds
from .engine import Action, Engine, pct_to_bri

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date

    from homeassistant.core import Event, EventStateChangedData

_LOGGER = logging.getLogger(__name__)
SUN = "sun.sun"


class Controller:
    """Owns settings, the live engine and (optionally) one demo run."""

    def __init__(self, hass: HomeAssistant, lights: list[str]) -> None:
        self.hass = hass
        self.lights = list(lights)
        self.values: dict[str, float] = dict(DEFAULTS)
        # per light: 0 means "use the global value"
        self.overrides: dict[str, dict[str, float]] = {
            light: {"normal": 0.0, "floor": 0.0} for light in self.lights
        }
        self.context = Context()
        self.engine = Engine(self._live_target)
        self.demo: Demo | None = None
        self.demo_light: str | None = None
        self.demo_engine: Engine | None = None
        self._demo_unsub: Callable[[], None] | None = None
        self._demo_restore: tuple[str, bool, int | None] | None = None
        # unsaved settings a demo is previewing (None = use the saved ones)
        self._demo_values: dict[str, float] | None = None
        self._demo_ov: dict[str, float] | None = None
        # choices made in the UI (the demo switch uses these)
        self.demo_choice: str | None = self.lights[0] if self.lights else None
        self.demo_loop = False
        self.demo_seconds = 0.0  # 0 = shortest cycle that keeps steps <= 1 %
        self._sun_prev: tuple[float, float] | None = None
        self._sun_last: tuple[float, float] | None = None
        self._sun_rising = False
        self._seen: set[str] = set()
        self._unsubs: list[Callable[[], None]] = []
        self._timer: Callable[[], None] | None = None
        self._pending: set[Callable[[], None]] = set()
        self._listeners: list[Callable[[], None]] = []

    # ---- lifecycle -----------------------------------------------------
    @callback
    def async_start(self) -> None:
        sun = self.hass.states.get(SUN)
        if sun is not None:
            self._push_sun(sun)
        self._unsubs.append(
            async_track_state_change_event(self.hass, [SUN], self._on_sun)
        )
        self._unsubs.append(
            async_track_state_change_event(self.hass, self.lights, self._on_light)
        )
        self._tick()

    @callback
    def async_stop(self) -> None:
        if self._timer:
            self._timer()
            self._timer = None
        for unsub in (*self._unsubs, *self._pending):
            unsub()
        self._unsubs.clear()
        self._pending.clear()
        if self._demo_unsub:
            self._demo_unsub()
            self._demo_unsub = None

    # ---- listeners for entities ---------------------------------------
    @callback
    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)

        def remove() -> None:
            if cb in self._listeners:
                self._listeners.remove(cb)

        return remove

    @callback
    def _notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    # ---- settings ------------------------------------------------------
    @callback
    def set_value(self, key: str, value: float, *, tick: bool = True) -> None:
        self.values[key] = float(value)
        if tick:
            self._tick()

    @callback
    def set_override(
        self, light: str, kind: str, value: float, *, tick: bool = True
    ) -> None:
        self.overrides.setdefault(light, {"normal": 0.0, "floor": 0.0})[kind] = float(
            value
        )
        if tick:
            self._tick()

    # ---- curve ---------------------------------------------------------
    def _pct(
        self,
        light: str,
        elevation: float,
        values: dict[str, float] | None = None,
        ov: dict[str, float] | None = None,
    ) -> float:
        values = values or self.values
        ov = self.overrides.get(light, {}) if ov is None else ov
        return curve.target_pct(
            elevation,
            start=values[K_START],
            end=values[K_END],
            normal=ov.get("normal") or values[K_NORMAL],
            floor=ov.get("floor") or values[K_FLOOR],
            sharp_start=values[K_SHARP_START],
            sharp_end=values[K_SHARP_END],
        )

    def live_elevation(self) -> float | None:
        if self._sun_last is None:
            return None
        return curve.interpolate_elevation(
            self._sun_prev, self._sun_last, dt_util.utcnow().timestamp()
        )

    def _live_target(self, light: str) -> float:
        elev = self.live_elevation()
        if elev is None:  # no sun data yet: assume daytime
            return self.values[K_NORMAL]
        return self._pct(light, elev)

    def _demo_target(self, light: str) -> float:
        elev = self.demo.elevation(time.monotonic()) if self.demo else None
        if elev is None:
            return self._live_target(light)
        return self._pct(light, elev, self._demo_values, self._demo_ov)

    def demo_elevation(self) -> float | None:
        """The sun elevation the running demo is showing, if one is running."""
        return self.demo.elevation(time.monotonic()) if self.demo else None

    def target_pct(self, light: str) -> float:
        if self.demo and light == self.demo_light:
            return self._demo_target(light)
        return self._live_target(light)

    def _in_ramp_window(
        self, elevation: float | None, values: dict[str, float] | None = None
    ) -> bool:
        values = values or self.values
        return elevation is not None and values[K_END] <= elevation < values[K_START]

    def holding(self, light: str) -> int | None:
        engine = self.demo_engine if light == self.demo_light else self.engine
        hold = engine.holds.get(light) if engine else None
        return hold.level if hold else None

    # ---- sun -----------------------------------------------------------
    def _push_sun(self, state) -> None:
        try:
            elev = float(state.attributes["elevation"])
        except KeyError, TypeError, ValueError:
            return
        ts = state.last_updated.timestamp()
        if self._sun_last is None or ts > self._sun_last[0]:
            self._sun_prev, self._sun_last = self._sun_last, (ts, elev)
        self._sun_rising = bool(state.attributes.get("rising"))

    @callback
    def _on_sun(self, event: Event[EventStateChangedData]) -> None:
        if (new := event.data["new_state"]) is not None:
            self._push_sun(new)
            self._tick()

    # ---- lights --------------------------------------------------------
    def _engine_for(self, light: str) -> Engine | None:
        if self.demo and light == self.demo_light:
            return self.demo_engine
        return self.engine if light in self.lights else None

    @callback
    def _on_light(self, event: Event[EventStateChangedData]) -> None:
        light = event.data["entity_id"]
        old, new = event.data["old_state"], event.data["new_state"]
        engine = self._engine_for(light)
        if engine is None or new is None or old is None:
            return
        actions = engine.observe(
            light,
            was_on=old.state == STATE_ON,
            is_on=new.state == STATE_ON,
            brightness=new.attributes.get(ATTR_BRIGHTNESS),
            now=time.monotonic(),
        )
        self._run(actions, delay=TURN_ON_DELAY_S)
        self._notify()

    @callback
    def _run(self, actions: list[Action], delay: float = 0.0) -> None:
        for action in actions:
            if delay:
                holder: list[Callable[[], None]] = []

                @callback
                def fire(_now, a=action, holder=holder) -> None:
                    self._pending.discard(holder[0])
                    self.hass.async_create_task(self._apply(a))

                holder.append(async_call_later(self.hass, delay, fire))
                self._pending.add(holder[0])
            else:
                self.hass.async_create_task(self._apply(action))

    async def _apply(self, action: Action) -> None:
        state = self.hass.states.get(action.light)
        if state is None or state.state != STATE_ON:
            return
        transition = TRANSITION_S
        if self.demo and action.light == self.demo_light:
            transition = min(TRANSITION_S, self.demo.tick_interval())
        await self.hass.services.async_call(
            "light",
            "turn_on",
            {
                ATTR_ENTITY_ID: action.light,
                ATTR_BRIGHTNESS: action.brightness,
                ATTR_TRANSITION: round(transition, 2),
            },
            blocking=False,
            context=self.context,
        )

    @callback
    def async_release(self, lights: list[str] | None = None) -> None:
        """Drop manual holds so the lights return to the curve."""
        for light in lights or self.lights:
            engine = self._engine_for(light)
            if engine:
                engine.release(light)
        self._tick()

    # ---- tick ----------------------------------------------------------
    def _light_state(self, light: str) -> tuple[bool, int | None]:
        state = self.hass.states.get(light)
        if state is None or state.state != STATE_ON:
            return False, None
        return True, state.attributes.get(ATTR_BRIGHTNESS)

    @callback
    def _tick(self, _now=None) -> None:
        if self._timer:
            self._timer()
            self._timer = None
        mono = time.monotonic()

        if self.demo and self.demo_engine and self.demo_light:
            elev = self.demo.elevation(mono)
            if elev is None:
                self.async_stop_demo()
            else:
                dawn = self.demo.rising(mono) and self._in_ramp_window(
                    elev, self._demo_values
                )
                states = {self.demo_light: self._light_state(self.demo_light)}
                self._run(self.demo_engine.tick(states, now=mono, dawn=dawn))

        states = {}
        for light in self.lights:
            if self.demo and light == self.demo_light:
                continue
            on, bri = self._light_state(light)
            if on and light not in self._seen and bri is not None:
                self.engine.adopt(light, True, bri)
            (self._seen.add if on else self._seen.discard)(light)
            states[light] = (on, bri)
        if self._sun_last is not None:
            dawn = self._sun_rising and self._in_ramp_window(self.live_elevation())
            self._run(self.engine.tick(states, now=mono, dawn=dawn))

        self._notify()
        interval = self.demo.tick_interval() if self.demo else TICK_S
        self._timer = async_call_later(self.hass, interval, self._tick)

    # ---- demo ----------------------------------------------------------
    def demo_ramp_seconds(
        self,
        light: str,
        total_s: float = 0.0,
        values: dict[str, float] | None = None,
        ov: dict[str, float] | None = None,
    ) -> float:
        """Real seconds for each ramp: from `total_s`, else the smoothest minimum."""
        if total_s > 0:
            return max(1.0, (total_s - 3 * HOLD_S) / 2)
        v = values or self.values
        swing = self._pct(light, v[K_START] + 1, v, ov) - self._pct(
            light, v[K_END] - 1, v, ov
        )
        return min_ramp_seconds(
            swing, curve.peak_slope(v[K_SHARP_START], v[K_SHARP_END])
        )

    def _clean_preview(
        self, light: str, preview: dict | None
    ) -> tuple[dict[str, float] | None, dict[str, float] | None]:
        """Validate and clamp unsaved settings sent by the panel."""
        if not preview:
            return None, None
        values = dict(self.values)
        limits = {key: (lo, hi) for key, _n, lo, hi, _s, _u in GLOBAL_NUMBERS}
        for key, raw in (preview.get("settings") or {}).items():
            if key in limits:
                lo, hi = limits[key]
                values[key] = min(hi, max(lo, float(raw)))
        ov = dict(self.overrides.get(light, {"normal": 0.0, "floor": 0.0}))
        for kind, raw in (preview.get("overrides") or {}).items():
            if kind in ("normal", "floor"):
                ov[kind] = min(100.0, max(0.0, float(raw)))
        return values, ov

    async def async_start_demo(
        self,
        light: str,
        *,
        seconds: float = 0.0,
        day: date | None = None,
        loop: bool = False,
        preview: dict | None = None,
    ) -> None:
        """Play one compressed dusk-and-dawn cycle of the real sun on one light.

        `seconds` is the whole cycle's length; 0 picks the shortest cycle in
        which no tick changes the brightness by more than about 1 %. `preview`
        holds unsaved settings to try instead of the saved ones:
        {"settings": {key: value}, "overrides": {"normal": n, "floor": f}}.
        """
        self.async_stop_demo()
        self._demo_values, self._demo_ov = self._clean_preview(light, preview)
        cfg = self.hass.config
        self.demo = Demo.cycle(
            lat=cfg.latitude,
            lon=cfg.longitude,
            tz=dt_util.get_default_time_zone(),
            day=day or dt_util.now().date(),
            start_hour=12,
            started_at=time.monotonic(),
            start_elev=(self._demo_values or self.values)[K_START],
            end_elev=(self._demo_values or self.values)[K_END],
            ramp_s=self.demo_ramp_seconds(
                light, seconds, self._demo_values, self._demo_ov
            ),
            loop=loop,
        )
        self.demo_light = light
        self.demo_engine = Engine(self._demo_target)
        state = self.hass.states.get(light)
        # Start where the light is now (off: the dawn ramp) and move at once.
        cur = state.attributes.get(ATTR_BRIGHTNESS) if state else None
        level = cur * 100 / 255 if state and state.state == STATE_ON and cur else None
        self.demo = replace(
            self.demo,
            start_offset_s=self.demo.start_offset(
                lambda e: self._pct(light, e, self._demo_values, self._demo_ov),
                level,
                high=self._pct(light, 90.0, self._demo_values, self._demo_ov),
                low=self._pct(light, -90.0, self._demo_values, self._demo_ov),
            ),
        )
        self._demo_restore = (
            light,
            bool(state and state.state == STATE_ON),
            state.attributes.get(ATTR_BRIGHTNESS) if state else None,
        )
        if light in self.lights:
            self.engine.release(light)
            self._seen.discard(light)
        else:
            self._demo_unsub = async_track_state_change_event(
                self.hass, [light], self._on_light
            )
        # Start the demo light at the virtual moment's level (turning it on).
        bri = pct_to_bri(self._demo_target(light))
        await self.hass.services.async_call(
            "light",
            "turn_on",
            {ATTR_ENTITY_ID: light, ATTR_BRIGHTNESS: bri},
            blocking=True,
            context=self.context,
        )
        self.demo_engine.observe(
            light, was_on=False, is_on=True, brightness=bri, now=time.monotonic()
        )
        self._tick()

    @callback
    def async_stop_demo(self) -> None:
        light = self.demo_light
        restore, self._demo_restore = self._demo_restore, None
        self.demo = None
        self.demo_light = None
        self.demo_engine = None
        self._demo_values = None
        self._demo_ov = None
        if self._demo_unsub:
            self._demo_unsub()
            self._demo_unsub = None
        if light and light in self.lights:
            self.engine.release(light)
        if restore:
            self.hass.async_create_task(self._restore(*restore))
        self._notify()

    async def _restore(self, light: str, was_on: bool, bri: int | None) -> None:
        """Put the light back as it was before the demo."""
        try:
            if was_on:
                data = {ATTR_ENTITY_ID: light, ATTR_TRANSITION: 1}
                if bri is not None:
                    data[ATTR_BRIGHTNESS] = bri
                await self.hass.services.async_call(
                    "light", "turn_on", data, context=self.context
                )
            else:
                await self.hass.services.async_call(
                    "light", "turn_off", {ATTR_ENTITY_ID: light}, context=self.context
                )
        except HomeAssistantError:
            _LOGGER.warning("Could not restore %s after the demo", light)
