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
