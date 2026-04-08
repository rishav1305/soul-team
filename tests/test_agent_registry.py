"""
Tests for agent_registry.py — soul-team agent configuration loader.

Covers:
  - _resolve_config_path(): SOUL_TEAM_CONFIG env var, primary path, legacy, example, default
  - _load_config(): valid config, missing file, invalid TOML → empty dict
  - get_agent_names(): from config, empty config
  - get_agent_names_with_friday(): always includes 'friday'
  - get_valid_agents(): frozenset, system names included
  - get_agent_models(): agent → model mapping, default 'sonnet'
  - get_agent_machines(): agent → machine mapping, default 'local'

Run: pytest tests/test_agent_registry.py -v
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import agent_registry


# ── Helpers ───────────────────────────────────────────────────────────────────


MINIMAL_TOML = b"""
[team]
name = "test-team"
stagger_seconds = 10

[[agents]]
name = "pepper"
model = "sonnet"
machine = "local"

[[agents]]
name = "shuri"
model = "opus"
machine = "worker"
"""


@pytest.fixture
def config_file(tmp_path):
    """Valid config TOML in a temp directory."""
    f = tmp_path / "config.toml"
    f.write_bytes(MINIMAL_TOML)
    return f


@pytest.fixture
def env_config(config_file, monkeypatch):
    """Set SOUL_TEAM_CONFIG to a known valid config file."""
    monkeypatch.setenv("SOUL_TEAM_CONFIG", str(config_file))
    return config_file


# ── TestResolveConfigPath ─────────────────────────────────────────────────────


class TestResolveConfigPath:
    """_resolve_config_path() selects correct config file."""

    def test_env_var_takes_priority(self, config_file, monkeypatch):
        monkeypatch.setenv("SOUL_TEAM_CONFIG", str(config_file))
        result = agent_registry._resolve_config_path()
        assert result == config_file

    def test_env_var_ignored_if_path_missing(self, monkeypatch):
        monkeypatch.setenv("SOUL_TEAM_CONFIG", "/nonexistent/path.toml")
        # Must fall through to next resolution step, not crash
        result = agent_registry._resolve_config_path()
        assert isinstance(result, Path)

    def test_returns_path_object(self, monkeypatch):
        monkeypatch.delenv("SOUL_TEAM_CONFIG", raising=False)
        result = agent_registry._resolve_config_path()
        assert isinstance(result, Path)

    def test_fallback_to_example_when_no_user_config(self, monkeypatch, tmp_path):
        """If no user config exists, falls back to repo example or default."""
        monkeypatch.delenv("SOUL_TEAM_CONFIG", raising=False)
        # Patch HOME so primary/legacy don't exist
        monkeypatch.setattr(agent_registry, "HOME", tmp_path)
        result = agent_registry._resolve_config_path()
        # Must return a Path (even if nonexistent default)
        assert isinstance(result, Path)


# ── TestLoadConfig ────────────────────────────────────────────────────────────


class TestLoadConfig:
    """_load_config() loads and caches the TOML config dict."""

    def test_returns_dict_from_valid_config(self, env_config):
        data = agent_registry._load_config()
        assert isinstance(data, dict)

    def test_agents_list_present(self, env_config):
        data = agent_registry._load_config()
        assert "agents" in data
        assert len(data["agents"]) == 2

    def test_returns_empty_dict_on_missing_file(self, monkeypatch, tmp_path):
        """Patch _resolve_config_path to return a nonexistent file → empty dict."""
        missing = tmp_path / "nonexistent.toml"
        monkeypatch.setattr(agent_registry, "_resolve_config_path", lambda: missing)
        data = agent_registry._load_config()
        assert data == {}

    def test_returns_empty_dict_on_invalid_toml(self, monkeypatch, tmp_path):
        bad = tmp_path / "bad.toml"
        bad.write_bytes(b"[this is not valid {{{ toml")
        monkeypatch.setattr(agent_registry, "_resolve_config_path", lambda: bad)
        data = agent_registry._load_config()
        assert data == {}

    def test_does_not_raise_on_any_error(self, monkeypatch, tmp_path):
        """_load_config must be safe to call in all conditions."""
        missing = tmp_path / "missing.toml"
        monkeypatch.setattr(agent_registry, "_resolve_config_path", lambda: missing)
        # Must not raise
        agent_registry._load_config()


# ── TestGetAgentNames ─────────────────────────────────────────────────────────


class TestGetAgentNames:
    """get_agent_names() returns list of agent names from config."""

    def test_returns_correct_names(self, env_config):
        names = agent_registry.get_agent_names()
        assert "pepper" in names
        assert "shuri" in names

    def test_returns_list(self, env_config):
        names = agent_registry.get_agent_names()
        assert isinstance(names, list)

    def test_empty_list_on_missing_config(self, monkeypatch, tmp_path):
        missing = tmp_path / "missing.toml"
        monkeypatch.setattr(agent_registry, "_resolve_config_path", lambda: missing)
        assert agent_registry.get_agent_names() == []

    def test_filters_agents_without_name(self, monkeypatch, tmp_path):
        """Agents with no 'name' field must be excluded."""
        f = tmp_path / "config.toml"
        f.write_bytes(b'[[agents]]\nmodel = "sonnet"\n[[agents]]\nname = "valid"\n')
        monkeypatch.setenv("SOUL_TEAM_CONFIG", str(f))
        names = agent_registry.get_agent_names()
        assert names == ["valid"]


# ── TestGetAgentNamesWithFriday ───────────────────────────────────────────────


class TestGetAgentNamesWithFriday:
    """get_agent_names_with_friday() always includes 'friday'."""

    def test_includes_friday(self, env_config):
        names = agent_registry.get_agent_names_with_friday()
        assert "friday" in names

    def test_includes_all_config_agents(self, env_config):
        names = agent_registry.get_agent_names_with_friday()
        assert "pepper" in names
        assert "shuri" in names

    def test_friday_not_duplicated_if_in_config(self, monkeypatch, tmp_path):
        """If 'friday' is already in config, should not appear twice."""
        f = tmp_path / "config.toml"
        f.write_bytes(b"[[agents]]\nname = 'friday'\n[[agents]]\nname = 'pepper'\n")
        monkeypatch.setenv("SOUL_TEAM_CONFIG", str(f))
        names = agent_registry.get_agent_names_with_friday()
        assert names.count("friday") == 1

    def test_returns_list(self, env_config):
        assert isinstance(agent_registry.get_agent_names_with_friday(), list)


# ── TestGetValidAgents ────────────────────────────────────────────────────────


class TestGetValidAgents:
    """get_valid_agents() returns frozenset including system names."""

    def test_returns_frozenset(self, env_config):
        assert isinstance(agent_registry.get_valid_agents(), frozenset)

    def test_includes_config_agents(self, env_config):
        valid = agent_registry.get_valid_agents()
        assert "pepper" in valid
        assert "shuri" in valid

    def test_includes_system_names(self, env_config):
        """System identifiers must always be in the valid set."""
        valid = agent_registry.get_valid_agents()
        assert "friday" in valid
        assert "team-lead" in valid
        assert "system" in valid
        assert "unknown" in valid

    def test_immutable_frozenset(self, env_config):
        valid = agent_registry.get_valid_agents()
        with pytest.raises(AttributeError):
            valid.add("intruder")  # type: ignore


# ── TestGetAgentModels ────────────────────────────────────────────────────────


class TestGetAgentModels:
    """get_agent_models() returns agent → model mapping."""

    def test_returns_dict(self, env_config):
        assert isinstance(agent_registry.get_agent_models(), dict)

    def test_correct_model_for_agent(self, env_config):
        models = agent_registry.get_agent_models()
        assert models["pepper"] == "sonnet"
        assert models["shuri"] == "opus"

    def test_default_sonnet_when_model_absent(self, monkeypatch, tmp_path):
        f = tmp_path / "config.toml"
        f.write_bytes(b"[[agents]]\nname = 'happy'\n")
        monkeypatch.setenv("SOUL_TEAM_CONFIG", str(f))
        models = agent_registry.get_agent_models()
        assert models["happy"] == "sonnet"

    def test_empty_dict_on_missing_config(self, monkeypatch, tmp_path):
        missing = tmp_path / "missing.toml"
        monkeypatch.setattr(agent_registry, "_resolve_config_path", lambda: missing)
        assert agent_registry.get_agent_models() == {}


# ── TestGetAgentMachines ──────────────────────────────────────────────────────


class TestGetAgentMachines:
    """get_agent_machines() returns agent → machine mapping."""

    def test_returns_dict(self, env_config):
        assert isinstance(agent_registry.get_agent_machines(), dict)

    def test_correct_machine_for_agent(self, env_config):
        machines = agent_registry.get_agent_machines()
        assert machines["pepper"] == "local"
        assert machines["shuri"] == "worker"

    def test_default_local_when_machine_absent(self, monkeypatch, tmp_path):
        f = tmp_path / "config.toml"
        f.write_bytes(b"[[agents]]\nname = 'happy'\n")
        monkeypatch.setenv("SOUL_TEAM_CONFIG", str(f))
        machines = agent_registry.get_agent_machines()
        assert machines["happy"] == "local"

    def test_empty_dict_on_missing_config(self, monkeypatch, tmp_path):
        missing = tmp_path / "missing.toml"
        monkeypatch.setattr(agent_registry, "_resolve_config_path", lambda: missing)
        assert agent_registry.get_agent_machines() == {}
