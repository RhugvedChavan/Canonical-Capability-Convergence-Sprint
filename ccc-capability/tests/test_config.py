import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from app.config import Settings, get_settings


def test_settings_have_sensible_defaults():
    s = Settings(_env_file=None)
    assert s.environment == "development"
    assert s.database_url.startswith("sqlite")
    assert s.port == 8000
    assert s.log_format == "json"


def test_settings_env_prefix_overrides_default(monkeypatch):
    monkeypatch.setenv("CWCC_PORT", "9001")
    monkeypatch.setenv("CWCC_ENVIRONMENT", "production")
    s = Settings(_env_file=None)
    assert s.port == 9001
    assert s.environment == "production"


def test_settings_adapter_toggles_default_enabled():
    s = Settings(_env_file=None)
    assert s.enable_bucket_adapter is True
    assert s.enable_replay_adapter is True
    assert s.enable_insightflow_adapter is True
    assert s.enable_runtime_registry_adapter is True
    assert s.enable_rajya_adapter is True


def test_settings_adapter_toggle_can_be_disabled(monkeypatch):
    monkeypatch.setenv("CWCC_ENABLE_BUCKET_ADAPTER", "false")
    s = Settings(_env_file=None)
    assert s.enable_bucket_adapter is False


def test_get_settings_is_cached():
    a = get_settings()
    b = get_settings()
    assert a is b


def test_settings_boolean_env_parsing(monkeypatch):
    monkeypatch.setenv("CWCC_DATABASE_ECHO", "true")
    s = Settings(_env_file=None)
    assert s.database_echo is True


def test_settings_invalid_boolean_raises(monkeypatch):
    monkeypatch.setenv("CWCC_DATABASE_ECHO", "not-a-bool")
    with pytest.raises(Exception):
        Settings(_env_file=None)


def test_invalid_environment_value_raises():
    with pytest.raises(Exception):
        Settings(_env_file=None, environment="bogus-env")


def test_invalid_log_format_value_raises():
    with pytest.raises(Exception):
        Settings(_env_file=None, log_format="xml")


def test_port_out_of_range_raises():
    with pytest.raises(Exception):
        Settings(_env_file=None, port=99999)


def test_port_zero_raises():
    with pytest.raises(Exception):
        Settings(_env_file=None, port=0)


def test_blank_database_url_raises():
    with pytest.raises(Exception):
        Settings(_env_file=None, database_url="   ")


def test_log_level_is_normalized_to_uppercase():
    s = Settings(_env_file=None, log_level="debug")
    assert s.log_level == "DEBUG"


def test_unknown_log_level_raises():
    with pytest.raises(Exception):
        Settings(_env_file=None, log_level="not-a-level")
