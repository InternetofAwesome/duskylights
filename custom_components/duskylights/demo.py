"""Demo mode: run a virtual 24 hours of sun over any real duration.

Pure logic. The Home Assistant glue swaps the live sun reading for
`Demo.elevation(now)` and ticks at `Demo.tick_interval()` while a demo runs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo

from .solar import elevation as solar_elevation

DAY_S = 86400.0
MIN_TICK_S = 0.25
MAX_TICK_S = 15.0
VIRTUAL_STEP_S = 120.0  # aim for no more than ~2 virtual minutes per tick
HOLD_S = 1.5  # real seconds spent on each flat stretch of a compressed cycle
STEP_PCT = 1.0  # largest brightness jump allowed per tick when auto-sizing


def min_ramp_seconds(
    swing_pct: float,
    peak_slope: float,
    tick_s: float = MIN_TICK_S,
    step_pct: float = STEP_PCT,
) -> float:
    """Shortest real duration of one ramp that keeps every tick under `step_pct`."""
    return max(1.0, swing_pct * peak_slope * tick_s / step_pct)


@dataclass(frozen=True)
class Demo:
    """A running demo. `now` is any monotonic real-time clock in seconds."""

    lat: float
    lon: float
    virtual_start: datetime  # timezone-aware: the virtual moment demo time zero shows
    started_at: float  # real clock reading when the demo began
    duration_s: float  # real seconds for one full 24 h of virtual time
    loop: bool = False
    # Optional (real_s, virtual_s) keyframes; empty means a uniform 24 h.
    keys: tuple[tuple[float, float], ...] = ()
    tick_s: float | None = None  # fixed tick interval, if set
    start_offset_s: float = (
        0.0  # real seconds into the cycle at which `started_at` sits
    )

    @classmethod
    def cycle(
        cls,
        *,
        lat: float,
        lon: float,
        tz: tzinfo,
        day: date,
        start_hour: float,
        started_at: float,
        start_elev: float,
        end_elev: float,
        ramp_s: float,
        hold_s: float = HOLD_S,
        tick_s: float = MIN_TICK_S,
        loop: bool = False,
    ) -> Demo:
        """A compressed day: only the dusk and dawn ramps play at length.

        The flat stretches before, between and after the ramps are skipped in
        `hold_s` each, so a whole cycle is about 2 * ramp_s + 3 * hold_s long.
        """
        start = datetime.combine(day, time(), tzinfo=tz) + timedelta(hours=start_hour)
        total = 2 * ramp_s + 3 * hold_s
        step = 60
        runs: list[list[float]] = []  # [first, last, first_elev, last_elev]
        inside = False
        for t in range(0, int(DAY_S) + 1, step):
            e = solar_elevation(lat, lon, start + timedelta(seconds=t))
            if end_elev <= e < start_elev:
                if inside:
                    runs[-1][1], runs[-1][3] = t, e
                else:
                    runs.append([t, t, e, e])
                inside = True
            else:
                inside = False
        dusk = next((r for r in runs if r[3] < r[2]), None)
        dawn = next((r for r in runs if r[3] > r[2] and r is not dusk), None)
        if dusk is None or dawn is None:  # polar day/night: no ramps to compress
            return cls(lat, lon, start, started_at, total, loop, (), tick_s)
        d0, d1 = max(0.0, dusk[0] - step), min(DAY_S, dusk[1] + step)
        r0, r1 = max(0.0, dawn[0] - step), min(DAY_S, dawn[1] + step)
        t1 = hold_s
        t2 = t1 + ramp_s
        t3 = t2 + hold_s
        t4 = t3 + ramp_s
        keys = ((0.0, 0.0), (t1, d0), (t2, d1), (t3, r0), (t4, r1), (total, DAY_S))
        return cls(lat, lon, start, started_at, total, loop, keys, tick_s)

    @classmethod
    def for_day(
        cls,
        *,
        lat: float,
        lon: float,
        tz: tzinfo,
        day: date,
        start_hour: float,
        started_at: float,
        duration_s: float,
        loop: bool = False,
    ) -> Demo:
        """Demo of the real sun on `day` (so it matches that time of year).

        The virtual day starts at `start_hour` local time on `day` and runs 24
        virtual hours from there, so a noon start shows dusk, night, then dawn.
        """
        start = datetime.combine(day, time(), tzinfo=tz) + timedelta(hours=start_hour)
        return cls(lat, lon, start, started_at, duration_s, loop)

    @property
    def speed(self) -> float:
        """Virtual seconds per real second."""
        return DAY_S / self.duration_s

    def progress(self, now: float) -> float | None:
        """Fraction of the virtual day elapsed, or None once a one-shot demo ends."""
        p = (now - self.started_at + self.start_offset_s) / self.duration_s
        if p >= 1.0 and not self.loop:
            return None
        p = p % 1.0 if self.loop else max(0.0, p)
        return self._fraction_at(p * self.duration_s)

    def _fraction_at(self, real: float) -> float:
        """Fraction of the virtual day shown `real` seconds into the cycle."""
        if not self.keys:
            return real / self.duration_s
        return self._virtual_offset(real) / DAY_S

    def elevation_at(self, real: float) -> float:
        """Sun elevation `real` seconds into the cycle (ignores the start offset)."""
        vt = self.virtual_start + timedelta(seconds=self._fraction_at(real) * DAY_S)
        return solar_elevation(self.lat, self.lon, vt)

    def offset_for_level(
        self, pct_at: Callable[[float], float], level: float, step: float = 0.05
    ) -> float:
        """Real seconds into the cycle where the dusk ramp reaches `level` percent.

        A light that is already dimmer than the daytime level starts part-way
        down the dusk ramp; one at or below the low level starts on the low
        plateau; one at or above the high level starts at the top (0).
        """
        limit = self.keys[3][0] if len(self.keys) > 3 else self.duration_s / 2
        t = 0.0
        while t < limit:
            if pct_at(self.elevation_at(t)) <= level + 0.5:
                return t
            t += step
        return self.keys[2][0] if len(self.keys) > 2 else 0.0

    def _virtual_offset(self, real: float) -> float:
        for (r0, v0), (r1, v1) in zip(self.keys, self.keys[1:], strict=False):
            if real <= r1:
                return v1 if r1 <= r0 else v0 + (v1 - v0) * (real - r0) / (r1 - r0)
        return self.keys[-1][1]

    def virtual_time(self, now: float) -> datetime | None:
        p = self.progress(now)
        if p is None:
            return None
        return self.virtual_start + timedelta(seconds=p * DAY_S)

    def elevation(self, now: float) -> float | None:
        vt = self.virtual_time(now)
        return None if vt is None else solar_elevation(self.lat, self.lon, vt)

    def rising(self, now: float) -> bool:
        """True while the sun is climbing (before solar noon)."""
        vt = self.virtual_time(now)
        if vt is None:
            return False
        later = vt + timedelta(minutes=5)
        return solar_elevation(self.lat, self.lon, later) > solar_elevation(
            self.lat, self.lon, vt
        )

    def tick_interval(self) -> float:
        """Real seconds between controller ticks so steps stay small and smooth."""
        if self.tick_s is not None:
            return self.tick_s
        return min(MAX_TICK_S, max(MIN_TICK_S, VIRTUAL_STEP_S / self.speed))
