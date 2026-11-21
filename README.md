# Dusky Lights

A Home Assistant integration that keeps your lights at a normal level during the
day and eases them down as the sun sets, following solar *elevation* (not clock
time), then back up at dawn.

**Status: early development.** The full integration is written and passes its
tests in Home Assistant's own test harness (config flow, entities, curve, holds,
release, overrides, demo), but it has **not yet been run against real lights**.
Treat it as pre-release.

## Install (HACS)

1. HACS → ⋮ → **Custom repositories** → add
   `https://github.com/InternetofAwesome/duskylights`, category **Integration**.
2. Download **Dusky Lights** in HACS, then restart Home Assistant.
3. Settings → Devices & services → **Add integration** → Dusky Lights, and pick
   the lights to manage. (Start with one.)

## Entities

Each managed light gets its own device, "Dusky <light name>", so ids stay short:
`number.dusky_<light>_high`, `number.dusky_<light>_low`,
`button.dusky_<light>_release`, `sensor.dusky_<light>_target`. Global settings
live on the "Dusky" device: `number.dusky_high`, `number.dusky_low`,
`number.dusky_start_elevation`, `number.dusky_end_elevation`,
`number.dusky_start_sharpness`, `number.dusky_end_sharpness`,
`button.dusky_release_all`, `sensor.dusky_sun_elevation`.

- Numbers (global): start/end elevation, high (normal) and low (minimum)
  brightness, sharpness at each end.
- Numbers (per light): high / low override. **0 = use the global value.**
- Buttons: release one light, or all, back onto the curve.
- Sensors: each light's target brightness (with `holding`, `hold_brightness` and
  `demo` attributes) and the interpolated sun elevation in use.

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

    python3 -m venv .venv && .venv/bin/pip install pytest-homeassistant-custom-component
    .venv/bin/python -m pytest -q
    ruff check . && ruff format --check .

## Demo mode

`duskylights.demo` (service) runs a virtual 24 hours of the *real sun for the
chosen date* (default today, so it matches the time of year) over any real
duration, e.g. 10 minutes. It drives exactly **one** light: `entity_id` is
required and must be a single light, and no other light is touched. Options:
`duration` (real minutes for the full day), `date`, `start_hour` (default 12:
dusk, night, then dawn) and `loop`. While it runs, that light's controller ticks
every fraction of a second so steps stay small, then it returns to the live sun.
Stop it early with `duskylights.demo_stop`.

## License

Copyright (c) 2026 InternetofAwesome.
[GNU AGPL-3.0](LICENSE). Free to use, modify and share, including commercially,
provided the copyright notice is kept and any distributed or network-served
modified version is published under the same license with its source. If you want
to use it in a closed-source product, a separate commercial license is available
from the author: open an issue on this repository.
