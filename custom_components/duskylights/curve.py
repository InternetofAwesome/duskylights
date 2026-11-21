"""Pure maths for the dusk dimming curve. No Home Assistant imports.

The curve is a cubic Hermite from 1 (normal) at x=0 to 0 (floor) at x=1, where
x is how far the sun has moved through the elevation window. The two sharpness
values are the slope at each end relative to a straight line:

    0 -> flat tangent (soft start/arrival), 1 -> same slope as a straight line,
    3 -> the steepest slope that stays monotonic (no overshoot).

    f(x) = (2x^3 - 3x^2 + 1) - a*(x^3 - 2x^2 + x) - b*(x^3 - x^2)

a = sharpness at the "normal" end, b = sharpness at the floor end.
a = b = 1 is exactly a straight line; a = b = 0 is smoothstep.
"""

from __future__ import annotations

MAX_SHARPNESS = 3.0
MIN_SEGMENT_S = 30.0  # readings closer than this give a meaningless slope
MAX_SEGMENT_S = 1800.0  # readings further apart than this are stale


def progress(elevation: float, start: float, end: float) -> float:
    """0 at/above `start`, 1 at/below `end`, linear in elevation between."""
    if start <= end:
        return 0.0
    return min(1.0, max(0.0, (start - elevation) / (start - end)))


def shape(x: float, a: float = 0.0, b: float = 0.0) -> float:
    """Curve value in [0, 1] for progress x (1 = normal, 0 = floor)."""
    a = min(MAX_SHARPNESS, max(0.0, a))
    b = min(MAX_SHARPNESS, max(0.0, b))
    x = min(1.0, max(0.0, x))
    h00 = 2 * x**3 - 3 * x**2 + 1
    h10 = x**3 - 2 * x**2 + x
    h11 = x**3 - x**2
    return min(1.0, max(0.0, h00 - a * h10 - b * h11))


def target_pct(
    elevation: float,
    start: float,
    end: float,
    normal: float,
    floor: float,
    sharp_start: float = 0.0,
    sharp_end: float = 0.0,
) -> float:
    """Brightness in percent for a given sun elevation."""
    floor = min(floor, normal)
    f = shape(progress(elevation, start, end), sharp_start, sharp_end)
    return floor + (normal - floor) * f


def interpolate_elevation(
    prev: tuple[float, float] | None,
    last: tuple[float, float],
    now: float,
) -> float:
    """Estimate the elevation at `now` from the last two sun readings.

    Each reading is (timestamp_seconds, elevation_degrees). The sun's angle is
    near-linear over a few minutes, so extrapolating the last segment removes
    the staircase from the sun entity's 2-4 minute update cadence. With only
    one reading, or a pair too close together or too far apart to give a
    trustworthy slope, it returns the last value unchanged.
    """
    t1, e1 = last
    if prev is None:
        return e1
    t0, e0 = prev
    if (t1 - t0) < MIN_SEGMENT_S or (t1 - t0) > MAX_SEGMENT_S or now < t1:
        return e1
    rate = (e1 - e0) / (t1 - t0)
    return e1 + rate * min(now - t1, 2 * (t1 - t0))  # never extrapolate far
