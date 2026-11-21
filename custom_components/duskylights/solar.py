"""Solar elevation from latitude, longitude and time (NOAA approximation).

Accurate to roughly 0.2 degrees, which is plenty for dimming. Normal operation
uses Home Assistant's `sun` entity; this exists so demo mode can run the sun
through a whole day at any speed.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime


def elevation(lat: float, lon: float, when: datetime) -> float:
    """Sun elevation in degrees above the horizon at `when` (timezone-aware)."""
    u = when.astimezone(UTC)
    day = u.timetuple().tm_yday
    g = 2 * math.pi / 365 * (day - 1 + (u.hour - 12) / 24 + u.minute / 1440)
    eqt = 229.18 * (
        0.000075
        + 0.001868 * math.cos(g)
        - 0.032077 * math.sin(g)
        - 0.014615 * math.cos(2 * g)
        - 0.040849 * math.sin(2 * g)
    )
    decl = (
        0.006918
        - 0.399912 * math.cos(g)
        + 0.070257 * math.sin(g)
        - 0.006758 * math.cos(2 * g)
        + 0.000907 * math.sin(2 * g)
        - 0.002697 * math.cos(3 * g)
        + 0.00148 * math.sin(3 * g)
    )
    minutes = u.hour * 60 + u.minute + u.second / 60
    hour_angle = math.radians((minutes + eqt + 4 * lon) / 4 - 180)
    la = math.radians(lat)
    return math.degrees(
        math.asin(
            math.sin(la) * math.sin(decl)
            + math.cos(la) * math.cos(decl) * math.cos(hour_angle)
        )
    )
