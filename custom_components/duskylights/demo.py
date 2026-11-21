"""Demo mode: run a virtual 24 hours of sun over any real duration.

Pure logic. The Home Assistant glue swaps the live sun reading for
`Demo.elevation(now)` and ticks at `Demo.tick_interval()` while a demo runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo

from .solar import elevation as solar_elevation

DAY_S = 86400.0
MIN_TICK_S = 0.25
MAX_TICK_S = 15.0
VIRTUAL_STEP_S = 120.0  # aim for no more than ~2 virtual minutes per tick


@dataclass(frozen=True)
class Demo:
    """A running demo. `now` is any monotonic real-time clock in seconds."""

    lat: float
    lon: float
    virtual_start: datetime  # timezone-aware: the virtual moment demo time zero shows
    started_at: float  # real clock reading when the demo began
    duration_s: float  # real seconds for one full 24 h of virtual time
    loop: bool = False

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
        p = (now - self.started_at) / self.duration_s
        if p >= 1.0 and not self.loop:
            return None
        return p % 1.0 if self.loop else max(0.0, p)

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
        return min(MAX_TICK_S, max(MIN_TICK_S, VIRTUAL_STEP_S / self.speed))
