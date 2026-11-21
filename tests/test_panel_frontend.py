"""Panel front end, run in headless Chrome against a fake `hass` (tests/panel/)."""

from __future__ import annotations

import html
import json
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


def test_panel_renders_and_drives_entities():
    page = dom(f"{HARNESS}?act=1")
    calls = out(page)
    sets = {c[2]["entity_id"]: c[2]["value"] for c in calls if c[1] == "set_value"}
    assert sets["number.dusky_high"] == 60
    assert sets["number.dusky_start_elevation"] == 12
    assert sets["number.dusky_living_high"] == 65
    pressed = [c[2]["entity_id"] for c in calls if c[0] == "button"]
    assert pressed == ["button.dusky_kitchen_release", "button.dusky_release_all"]
    assert ["switch", "turn_on", {"entity_id": "switch.dusky_demo"}] in calls
