import pytest

from november_whiskey.config import load_config
from november_whiskey.exceptions import ConfigError


def test_config_validation_missing(monkeypatch):
    monkeypatch.setenv("AUDIENCE_ENV_PATH", "tests/fixtures/missing-segment.env")
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)
    with pytest.raises(ConfigError):
        load_config()


def test_config_validation_missing_segment_file(monkeypatch):
    monkeypatch.setenv("HUBSPOT_TOKEN", "x")
    monkeypatch.setenv("HUBSPOT_APP_ID", "2286")
    monkeypatch.setenv("TENANT_ID", "x")
    monkeypatch.setenv("CLIENT_ID", "x")
    monkeypatch.setenv("CLIENT_SECRET", "x")
    monkeypatch.setenv("MIKE_ID", "mike@example.com")
    monkeypatch.setenv("AUDIENCE_ENV_PATH", "tests/fixtures/does-not-exist.env")
    with pytest.raises(ConfigError, match="Missing audience config file"):
        load_config()


def test_config_validation_invalid_audience_segments_value(monkeypatch):
    monkeypatch.setenv("AUDIENCE_SEGMENTS", "private-lenders,../bad-segment")
    with pytest.raises(ConfigError, match="path traversal is not allowed"):
        load_config()


def test_config_validation_empty_cli_segments_override():
    from november_whiskey.config import resolve_audience_segments

    with pytest.raises(ConfigError, match="CLI --segments override was provided but no valid segments were found"):
        resolve_audience_segments("  ,  ")
