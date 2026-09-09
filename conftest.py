"""All repository pytest runs require the shared isolation launcher."""
from kronos_test_isolation import install

_ISOLATION = install(required=True)

import shutil
from pathlib import Path
import pytest


def pytest_configure(config):
    config.option.basetemp = str(Path(_ISOLATION['root']) / 'pytest')
    if config.pluginmanager.hasplugin('cacheprovider'):
        config.inicfg['cache_dir'] = str(Path(_ISOLATION['root']) / 'cache')


@pytest.fixture(autouse=True)
def isolated_default_store_home():
    """A default store can never carry state between otherwise isolated tests."""
    home = Path(_ISOLATION['home'])
    home.mkdir(parents=True, exist_ok=True)
    yield
    if home.exists():
        shutil.rmtree(home)
