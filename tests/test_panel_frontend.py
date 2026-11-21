"""Panel front end, run in headless Chrome against a fake `hass` (tests/panel/)."""

from __future__ import annotations

import html
import json
import math
import re
import shutil
import subprocess
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
CHROME = shutil.which("google-chrome") or shutil.which("chromium")
pytestmark = pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium installed")

import sys

sys.path.insert(0, str(ROOT / "custom_components"))
from duskylights import curve

HARNESS = (ROOT / "tests" / "panel" / "harness.html").as_uri()


def dom(url: str) -> str:
    return subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--allow-file-access-from-files",
            "--virtual-time-budget=4000",
            "--dump-dom",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    ).stdout


def out(page: str):
    found = re.findall(r'<pre id="out">(.*?)</pre>', page, re.DOTALL)
    assert found, page[:500]
    return json.loads(html.unescape(found[-1]))  # the last one is the rendered DOM


def test_js_curve_matches_python():
    cases = [
        (x / 20, a, b)
        for x in range(21)
        for a, b in ((0, 0), (1, 1), (3, 3), (0.5, 2), (2, 0.5), (-1, 5))
    ]
    q = urllib.parse.urlencode({"mode": "parity", "cases": json.dumps(cases)})
    got = out(dom(f"{HARNESS}?{q}"))
    want = [curve.shape(x, a, b) for x, a, b in cases]
    assert len(got) == len(want)
    for g, w in zip(got, want, strict=True):
        assert g == pytest.approx(w, abs=1e-9)


def test_edits_are_a_draft_until_saved_and_the_demo_previews_them():
    result = out(dom(f"{HARNESS}?act=1"))
    calls, before = result["calls"], result["beforeSave"]
    assert calls[:before] == []  # editing wrote nothing
    ws = [c for c in calls if c[0] == "ws"]
    assert [c[1] for c in ws] == ["duskylights/demo"]
    preview = ws[0][2]["preview"]
    assert preview["settings"]["normal_pct"] == 60  # the unsaved values
    assert preview["settings"]["start_elevation"] == 12
    assert preview["overrides"]["normal"] == 65
    sets = {c[2]["entity_id"]: c[2]["value"] for c in calls if c[1] == "set_value"}
    assert sets == {"number.dusky_high": 55}  # discard dropped the rest
    pressed = [c[2]["entity_id"] for c in calls if c[0] == "button"]
    assert pressed == ["button.dusky_kitchen_release", "button.dusky_release_all"]


def probe(**flags):
    q = urllib.parse.urlencode({"probe": 1, **flags})
    return out(dom(f"{HARNESS}?{q}"))


def test_clock_times_match_the_suns_path_and_the_locale():
    # fake sun: elevation = 40 cos(2 pi (h - 12) / 24) - 8, UTC, 24-hour clock.
    # 10 degrees is reached (going down) when cos = 18/40 -> 16:13; -6 degrees
    # when cos = 2/40 -> 17:48; the morning mirrors that around noon.
    r = probe()
    assert r["errors"] == []
    assert "16:13" in r["svg"]
    assert "Today's sun: dimming runs 16:13 to 17:48" in r["times"]
    assert "brightening runs 6:11 to 7:46" in r["times"]


def test_sun_that_never_crosses_the_elevations_is_explained_not_broken():
    r = probe(polar=1)
    assert r["errors"] == [] and r["rendered"]
    assert not any(":" in t for t in r["svg"])  # no clock times drawn
    assert "doesn't pass through both" in r["times"]


def test_unavailable_entities_do_not_break_the_panel():
    r = probe(unavail=1)
    assert r["errors"] == [] and r["rendered"]
    assert not any("NaN" in t for t in r["svg"])


def test_no_lights_still_renders_and_the_demo_is_disabled():
    r = probe(nolights=1)
    assert r["errors"] == [] and r["rendered"]
    assert r["goDisabled"] is True
    assert "Add a light" in r["note"]


def test_garbage_typed_into_the_fields_is_clamped_or_ignored():
    r = out(dom(f"{HARNESS}?garbage=1"))
    assert r["errors"] == []
    sets = {c[2]["entity_id"]: c[2]["value"] for c in r["calls"] if c[1] == "set_value"}
    assert sets["number.dusky_high"] == 100  # 999 clamped to the maximum
    assert sets["number.dusky_low"] == 1  # -5 clamped to the minimum
    assert sets["number.dusky_living_high"] == 100  # 250 clamped
    assert "number.dusky_end_elevation" not in sets  # "abc" ignored
    assert "number.dusky_start_elevation" not in sets  # empty ignored
    assert not any(math.isnan(v) for v in sets.values())  # no NaN written
    assert r["endBox"] != "abc"


def test_lights_are_added_and_removed_from_the_panel_and_locked_while_editing():
    r = out(dom(f"{HARNESS}?manage=1"))
    assert r["errors"] == []
    sets = [c[2]["lights"] for c in r["calls"] if c[1] == "duskylights/set_lights"]
    assert sets == [
        ["light.living", "light.kitchen", "light.office"],
        ["light.kitchen"],
    ]
    assert r["locked"] is True
    assert r["addState"] == [True, False]  # Add is off until a light is picked
    f = r["found"]
    assert len(f["all"]) == 3
    assert f["bySubstring"] == [
        "Office lightslight.office"
    ]  # "FFI" finds it mid-word, any case
    assert f["byEntity"] == ["Porchlight.porch"]
    assert f["noMatch"] == ["No matching lights"]
    assert f["value"] == "Office lights"  # arrow-down + Enter picked the second match


def test_picking_a_light_shows_its_own_curve_and_editing_it_moves_the_chart():
    r = out(dom(f"{HARNESS}?select=1"))
    assert r["errors"] == []
    assert r["picked"] != r["before"]  # now showing that light's curve
    assert r["edited"] != r["picked"]  # typing a new High redraws it live
    assert "Living lights" in r["legend"] and "Day 50%" in r["legend"]
    assert "Day 90%" in r["legend2"]
    assert r["back"] != r["edited"] and r["sel"] is None  # second click = all lights


def test_tooltips_are_our_own_delayed_and_explain_the_default():
    r = out(dom(f"{HARNESS}?tip=1"))
    assert r["errors"] == []
    assert r["early"] == "none" and r["shown"] == "block" and r["after"] == "none"
    assert "default (50%)" in r["text"]
    assert r["w"] < 420  # wraps rather than running across the page
    assert r["native"] == 0  # no browser-styled title tooltips left


def test_the_graph_glides_to_new_values_instead_of_jumping():
    r = out(dom(f"{HARNESS}?anim=1"))
    assert r["errors"] == []
    assert r["t0"] == r["start"]  # nothing has jumped the instant you change a value
    assert (
        r["mid"] != r["start"] and r["mid"] != r["end"]
    )  # partway there a moment later
    assert r["end"] != r["start"]
    assert (
        r["settled"] == r["end"] and r["raf"] is False
    )  # it lands and stops redrawing


def test_clicking_a_light_unlocks_only_its_brightness_and_locks_the_shared_settings():
    r = out(dom(f"{HARNESS}?perlight=1"))
    assert r["errors"] == []
    assert r["before"]["title"] == "Settings" and r["before"]["setAll"] is True
    assert r["before"]["start"]["disabled"] is False  # editing the shared settings
    p = r["picked"]
    assert p["title"] == "Settings: Kitchen lights" and p["setAll"] is False
    assert p["start"]["disabled"] and p["sharp"]["disabled"]  # shared: greyed out
    assert "shared by every light" in p["start"]["tip"]  # ...and it says why
    assert (
        not p["high"]["disabled"] and not p["low"]["disabled"]
    )  # brightness is the per-room part
    assert (
        p["high"]["shows"] == "70" and p["high"]["lnkHidden"] is False
    )  # its own, so Use default is offered
    assert r["mid"]["draft"] == {
        "number.dusky_kitchen_high": 85
    }  # this light, not the shared one
    assert r["reset"]["draft"] == {
        "number.dusky_kitchen_high": 85,
        "number.dusky_kitchen_low": 0,
    }  # 0 = shared
    assert r["preview"]["preview"]["overrides"] == {"normal": 85, "floor": 0}
    assert (
        r["preview"]["preview"]["settings"]["normal_pct"] == 50
    )  # the shared value untouched
    sets = {c[2]["entity_id"]: c[2]["value"] for c in r["calls"] if c[1] == "set_value"}
    assert sets == {"number.dusky_kitchen_high": 85, "number.dusky_kitchen_low": 0}
    assert (
        r["living"]["high"]["inherited"] and r["living"]["high"]["shows"] == "50"
    )  # grey = follows shared
    assert r["back"]["title"] == "Settings" and r["back"]["start"]["disabled"] is False


def test_the_sky_darkness_bands_are_labelled_ordered_and_carry_todays_times():
    r = probe()
    assert r["errors"] == []
    names = [b["tip"].split(" (")[0].split(".")[0] for b in r["bands"]]
    assert names == [
        "Day",
        "Civil twilight",
        "Nautical twilight",
        "Astronomical twilight",
        "Night",
    ]
    shades = [float(b["shade"]) for b in r["bands"]]
    assert (
        shades == sorted(shades) and shades[0] == 0
    )  # darker the further the sun is below the horizon
    civil = r["bands"][1]["tip"]
    assert "17:13" in civil and "17:48" in civil  # the 0 and -6 degree crossings
    assert [b.get("label") for b in r["bands"]][:2] == ["day", "civil"]
