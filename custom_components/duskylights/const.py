"""Constants for Dusky Lights."""

from __future__ import annotations

DOMAIN = "duskylights"
CONF_LIGHTS = "lights"

# Global setting keys
K_START = "start_elevation"
K_END = "end_elevation"
K_NORMAL = "normal_pct"
K_FLOOR = "floor_pct"
K_SHARP_START = "sharp_start"
K_SHARP_END = "sharp_end"

DEFAULTS: dict[str, float] = {
    K_START: 10.0,
    K_END: -6.0,
    K_NORMAL: 50.0,
    K_FLOOR: 10.0,
    K_SHARP_START: 0.0,
    K_SHARP_END: 0.0,
}

# key, name, min, max, step, unit
GLOBAL_NUMBERS: tuple[tuple[str, str, float, float, float, str | None], ...] = (
    (K_START, "Start elevation", -20, 40, 0.5, "°"),
    (K_END, "End elevation", -30, 20, 0.5, "°"),
    (K_NORMAL, "High", 1, 100, 1, "%"),
    (K_FLOOR, "Low", 1, 100, 1, "%"),
    (K_SHARP_START, "Start sharpness", 0, 3, 0.1, None),
    (K_SHARP_END, "End sharpness", 0, 3, 0.1, None),
)

TICK_S = 15.0  # normal controller tick
TRANSITION_S = 2.0  # light transition for our own commands
TURN_ON_DELAY_S = 0.5  # let a light finish turning on before we set its level

SERVICE_RELEASE = "release"
SERVICE_DEMO = "demo"
SERVICE_DEMO_STOP = "demo_stop"
