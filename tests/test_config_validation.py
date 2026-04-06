import pytest

from november_whiskey.config import load_config
from november_whiskey.exceptions import ConfigError


def test_config_validation_missing(monkeypatch):
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)
    with pytest.raises(ConfigError):
        load_config()
