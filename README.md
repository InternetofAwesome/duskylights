# Dusky Lights

A Home Assistant integration that keeps your lights at a normal level during the
day and eases them down as the sun sets, following solar *elevation* (not clock
time), then back up at dawn.

**Status: early development, not yet installable.** Only the curve maths exists
so far (`custom_components/duskylights/curve.py`, with tests).

## Design

- Each light sits at a "normal" brightness; as the sun drops through a window of
  elevations it eases down to a "minimum". Defaults: ramp starts at +10°, floor
  reached at -6° (end of civil twilight). Dawn is the mirror image.
- The curve is a cubic Hermite with a **sharpness** at each end: 0 = soft, 1 =
  straight line, up to 3 = steep (never overshoots).
- Global defaults, with optional per-room overrides (0 = use the global value).
- Manual changes: dimming by hand holds that level until the sun's target falls
  below it; raising by hand holds until the light is turned off and on, or dawn.
  Release buttons put a room (or all rooms) back on the curve.
- The sun entity updates only every few minutes, so elevation is interpolated
  between readings and changes are applied in ~1 % steps.
- No firmware or add-on dependencies: it only uses standard `light` entities and
  Home Assistant's built-in `sun` integration.

## Development

    python3 -m unittest discover -s tests -v
    ruff check . && ruff format --check .
