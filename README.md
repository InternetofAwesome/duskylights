<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="custom_components/duskylights/brand/dark_icon@2x.png">
    <img src="custom_components/duskylights/brand/icon@2x.png" alt="Dusky Lights" width="160">
  </picture>
</p>

<h1 align="center">Dusky Lights</h1>

<p align="center">
  Dims your lights along the sun's elevation: a set level during the day, a
  smooth ease down to a lower level at dusk, and back up at dawn.
</p>

<p align="center">
  <a href="https://github.com/InternetofAwesome/duskylights/actions/workflows/validate.yml"><img src="https://github.com/InternetofAwesome/duskylights/actions/workflows/validate.yml/badge.svg" alt="Validate"></a>
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg" alt="HACS Custom"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue.svg" alt="AGPL-3.0"></a>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/curve-dark.svg">
    <img src="assets/curve-light.svg" alt="Brightness eases from high to low as the sun drops from +10 to -6 degrees" width="720">
  </picture>
</p>

## What it does

| | |
|---|---|
| **Follows the sun, not the clock** | The ramp is defined by sun *elevation*, so it shifts with the seasons by itself. Default: starts at +10°, floor reached at -6°. |
| **Never brightens on you** | Dim a light by hand and it stays where you put it until the sun catches down, or you turn it off and on. |
| **Set it once, tune per room** | Global high and low, with per-room overrides. Overrides of 0 mean "use the global value". |
| **Smooth into the plateaus** | The ramp is a jerk-limited S-curve: it eases into the high and low levels with no kink. A sharpness control at each end shortens that easing, down to a straight line. |
| **Smooth** | Sun elevation is interpolated between updates; changes are applied in about 1 % steps. |
| **Try it fast** | Demo mode plays a whole day's sun, for today's date, over a few minutes on a single light. |
| **Plain Home Assistant** | Only `light` entities and the built-in `sun` integration. Nothing to flash. |

**Status: early development.** It passes its tests in Home Assistant's own test
harness (config flow, entities, curve, holds, release, overrides, demo) but has
not yet been run against real lights. Treat it as pre-release.

## The Dusky panel

Admins get a **Dusky** page in the sidebar (and it is the integration's configure
page where Home Assistant supports that). It shows the brightness curve for your
settings, redrawn as you drag the sliders, with the sun's current elevation and
each light's current target marked on it. Under the elevations are the clock times
at which today's sun passes them, so you can see when dimming will start and end. Below the graph are the global
settings, a table of lights (per-light high and low overrides, whether a light
is holding a manual level, a Release button for each) and the demo controls.

It reads and writes the integration's own entities, so everything on the panel
also works from dashboards and automations.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/panel-dark.png">
    <img src="assets/panel-light.png" alt="The Dusky panel: curve graph, settings, lights table and demo controls" width="820">
  </picture>
  <br><sub>Sample data.</sub>
</p>

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
- The curve is a jerk-limited S-curve: constant-jerk (cubic) easing into each
  plateau, so there is no kink where the ramp meets the high or low level. The
  **sharpness** at each end shortens that easing: 0 = longest and smoothest,
  1 = a straight line into the plateau.
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

## Choosing a low level

Dusky works in Home Assistant brightness percent. Some dimmers rescale that range
or need a minimum level to light a bulb, and Dusky does not know about either.
If your dimmer exposes a minimum, a maximum and a "strike" or "kick" level, keep
**Low** at or above the strike level in Home Assistant terms:

    (strike - min) / (max - min) x 100

For example, a dimmer that maps 0-100 % onto 15-94 % and strikes bulbs at 25 %
needs Low of at least (25 - 15) / (94 - 15) x 100 = 12.7 %. Use the per-light
**Low** override for lights that differ. A turn-on from off at a level below the
strike level will still flash at the strike level first; that is the dimmer's own
behaviour and is not something Dusky controls.

## Demo mode

Plays one compressed cycle of the real sun for today's date (or any `date`) on
exactly **one** light: the dusk ramp, a hold at the low level, the dawn ramp, and
a hold at the high level. It starts at the point nearest where the light is now
and begins moving at once: part-way down the dusk ramp if the light is between
the two levels, at the start of the dusk ramp if it is at the high level, and at
the start of the dawn ramp if it is at the low level or off. A one-shot runs one
full cycle from there, then puts the light back as it was.

With the default length it is the shortest cycle in which no step changes the
brightness by more than about 1 %: about 20 s per ramp at the default settings,
45 s or so in all. Softer curves take longer (about 20 s per ramp at the defaults).

From the UI (device "Dusky"): choose **Demo light**, **Demo repeat** (Once or
Loop) and **Demo length** (seconds, 0 = automatic), then turn on **Demo**.
Turning it off stops it.

From automations: `duskylights.demo` with `entity_id` (one light), optional
`seconds`, `date` and `loop`; `duskylights.demo_stop` ends it.

## License

Copyright (c) 2026 InternetofAwesome.
[GNU AGPL-3.0](LICENSE). Free to use, modify and share, provided the copyright
notice is kept and any distributed or network-served modified version is
published under the same license with its source.
