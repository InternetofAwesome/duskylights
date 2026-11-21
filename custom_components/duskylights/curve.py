"""Pure maths for the dusk dimming curve. No Home Assistant imports.

The curve runs from 1 (normal) at x=0 to 0 (floor) at x=1, where x is how far the
sun has moved through the elevation window. It is a jerk-limited ("S-curve")
ramp: the way into each plateau is a cubic with constant jerk, so the brightness
reaches the plateau with zero slope AND zero acceleration (no kink, no sudden
change of acceleration). The two sharpness values set how long that constant-jerk
entry lasts at each end, as a fraction of the ramp:

    sharpness 0 -> the longest entry, a quarter of the ramp (a pure four-phase
                   S-curve, steepest through the middle),
    sharpness 1 -> no entry at all: a straight line straight into the plateau.

Between the two entries the slope is constant. With entry fractions s (start) and
e (end), the middle slope is v = 1 / (1 - s - e); each entry is a pair of
constant-jerk pieces whose acceleration rises linearly then falls linearly to 0.
"""

from __future__ import annotations

MAX_SHARPNESS = 1.0
MAX_ENTRY = 0.25  # entry length at sharpness 0, as a fraction of the ramp
MIN_SEGMENT_S = 30.0  # readings closer than this give a meaningless slope
MAX_SEGMENT_S = 1800.0  # readings further apart than this are stale


def progress(elevation: float, start: float, end: float) -> float:
    """0 at/above `start`, 1 at/below `end`, linear in elevation between."""
    if start <= end:
        return 0.0
    return min(1.0, max(0.0, (start - elevation) / (start - end)))


def _entry(sharpness: float) -> float:
    """Length of the constant-jerk entry (fraction of the ramp) for a sharpness."""
    return MAX_ENTRY * (1.0 - min(MAX_SHARPNESS, max(0.0, sharpness)) / MAX_SHARPNESS)


def shape(x: float, a: float = 0.0, b: float = 0.0) -> float:
    """Curve value in [0, 1] for progress x (1 = normal, 0 = floor).

    `a` is the sharpness at the normal end, `b` at the floor end.
    """
    if x <= 0.0:
        return 1.0
    if x >= 1.0:
        return 0.0
    s, e = _entry(a), _entry(b)
    v = 1.0 / (1.0 - s - e)  # slope of the middle section
    # position travelled (0..1) along the ramp, built from constant-jerk pieces
    j1 = v / s**2 if s > 1e-12 else 0.0
    j2 = v / e**2 if e > 1e-12 else 0.0
    xc0, xc1 = 2 * s, 1 - 2 * e  # the constant-slope middle
    if s > 1e-12 and x < xc0:
        if x <= s:
            p = j1 * x**3 / 6
        else:
            t = x - s
            p = j1 * s**3 / 6 + (j1 * s**2 / 2) * t + j1 * s * t**2 / 2 - j1 * t**3 / 6
    elif e > 1e-12 and x > xc1:
        t = x - xc1
        p_c = v * (xc1 - 2 * s) + (j1 * s**3 if s > 1e-12 else 0.0)
        if t <= e:
            p = p_c + v * t - j2 * t**3 / 6
        else:
            u = t - e
            p_ce = p_c + v * e - j2 * e**3 / 6
            p = p_ce + (v / 2) * u - j2 * e * u**2 / 2 + j2 * u**3 / 6
    else:
        p = (j1 * s**3 if s > 1e-12 else 0.0) + v * (x - 2 * s)
    return min(1.0, max(0.0, 1.0 - p))


def peak_slope(a: float = 0.0, b: float = 0.0) -> float:
    """Steepest |d shape / d progress| over the ramp (2 at sharpness 0)."""
    return 1.0 / (1.0 - _entry(a) - _entry(b))


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
