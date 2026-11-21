from pathlib import Path

import pytest

import custom_components

# The test harness ships its own `custom_components` package that shadows ours;
# add this repo's folder so `custom_components.duskylights` resolves.
_repo = str(Path(__file__).parents[1] / "custom_components")
if _repo not in custom_components.__path__:
    custom_components.__path__.append(_repo)

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def no_real_frontend(hass_fixture_setup=None):
    """Our manifest depends on http/frontend/panel_custom; the harness has no
    frontend package, so mark the last two loaded (http is real) and stub the panel registration. The
    panel module is tested directly in test_panel.py."""
    from unittest.mock import AsyncMock, patch

    with (
        patch("custom_components.duskylights.async_register_panel", AsyncMock()),
        patch("custom_components.duskylights.async_remove_panel"),
    ):
        yield


@pytest.fixture(autouse=True)
def frontend_components_loaded(hass):
    hass.config.components.update({"frontend", "panel_custom"})
    yield
