"""
Tests for soul-team unified CLI: setup wizard, management subcommands, and state detection.

Covers:
- Config path resolution
- TOML loading/saving
- add-agent, remove-agent, list-agents subcommands
- add-machine, list-machines subcommands
- config view/set subcommand
- Template loading and model defaults
- Layout recalculation
- State detection (first_run, configured, running)
- Interactive menu fallback
- CLI flag parsing
"""
from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path
from unittest import mock

import pytest

# Add repo root to path so we can import soul-team as a module
REPO_ROOT = Path(__file__).resolve().parent.parent

# soul-team has no .py extension — use importlib with explicit loader
import importlib.util
import importlib.machinery

_soul_team_path = str(REPO_ROOT / "bin" / "soul-team")
_loader = importlib.machinery.SourceFileLoader("soul_init", _soul_team_path)
_spec = importlib.util.spec_from_loader("soul_init", _loader, origin=_soul_team_path)
soul_init = importlib.util.module_from_spec(_spec)
soul_init.__file__ = _soul_team_path
sys.modules["soul_init"] = soul_init
_spec.loader.exec_module(soul_init)


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def sample_toml(tmp_path):
    """Create a minimal valid TOML config."""
    toml_content = textwrap.dedent("""\
        [team]
        name = "test-team"
        description = "Test team"
        boot_prompt = "Do stuff."
        stagger_seconds = 5

        [policies]
        permission_mode = "bypassPermissions"
        guardian = true
        courier = true

        [[agents]]
        name = "dev-1"
        model = "sonnet"
        machine = "local"
        cgroup = true
        template = "developer"

        [[agents]]
        name = "research-1"
        model = "sonnet"
        machine = "local"
        cgroup = true
        template = "researcher"

        [layout]
        columns = 2
        rows = 2

        [[layout.grid]]
        col = 1
        agents = ["dev-1", "research-1"]
    """)
    toml_path = tmp_path / "config.toml"
    toml_path.write_text(toml_content)
    return toml_path


@pytest.fixture
def mock_home(tmp_path, monkeypatch):
    """Mock HOME to a temp directory with config structure."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".soul-team").mkdir()
    (home / ".claude" / "config").mkdir(parents=True)
    (home / ".claude" / "agents").mkdir(parents=True)

    monkeypatch.setattr(soul_init, "HOME", home)
    monkeypatch.setattr(soul_init, "USER_CONFIG_DIR", home / ".soul-team")
    monkeypatch.setattr(soul_init, "CLAUDE_CONFIG_DIR", home / ".claude" / "config")
    monkeypatch.setattr(soul_init, "CLAUDE_AGENTS_DIR", home / ".claude" / "agents")
    return home


# ── Config path resolution ──────────────────────────────────────────────────

class TestConfigPathResolution:

    def test_env_var_takes_priority(self, tmp_path, mock_home):
        """$SOUL_TEAM_CONFIG overrides all other paths."""
        env_config = tmp_path / "env-config.toml"
        env_config.write_text("[team]\nname = \"env\"\n")

        with mock.patch.dict(os.environ, {"SOUL_TEAM_CONFIG": str(env_config)}):
            result = soul_init._resolve_config_path()
            assert result == env_config

    def test_user_config_dir_primary(self, mock_home):
        """~/.soul-team/config.toml is primary when it exists."""
        primary = mock_home / ".soul-team" / "config.toml"
        primary.write_text("[team]\nname = \"primary\"\n")

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SOUL_TEAM_CONFIG", None)
            result = soul_init._resolve_config_path()
            assert result == primary

    def test_legacy_path_fallback(self, mock_home):
        """~/.claude/config/soul-team.toml used if primary doesn't exist."""
        legacy = mock_home / ".claude" / "config" / "soul-team.toml"
        legacy.write_text("[team]\nname = \"legacy\"\n")

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SOUL_TEAM_CONFIG", None)
            result = soul_init._resolve_config_path()
            assert result == legacy

    def test_default_to_primary_when_nothing_exists(self, mock_home):
        """Returns primary path as write target even when nothing exists."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SOUL_TEAM_CONFIG", None)
            result = soul_init._resolve_config_path()
            assert result == mock_home / ".soul-team" / "config.toml"


# ── TOML loading ────────────────────────────────────────────────────────────

class TestTomlLoading:

    def test_load_valid_toml(self, sample_toml):
        data = soul_init._load_toml(sample_toml)
        assert data["team"]["name"] == "test-team"
        assert len(data["agents"]) == 2
        assert data["agents"][0]["name"] == "dev-1"

    def test_load_toml_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            soul_init._load_toml(tmp_path / "nonexistent.toml")


# ── TOML saving (roundtrip) ────────────────────────────────────────────────

class TestTomlSaving:

    def test_save_and_reload(self, tmp_path):
        data = {
            "team": {"name": "roundtrip-team", "stagger_seconds": 15},
            "agents": [
                {"name": "agent-a", "model": "opus", "machine": "local", "cgroup": True},
            ],
        }
        out_path = tmp_path / "output.toml"
        soul_init._save_toml_from_dict(data, out_path)

        # Reload and verify
        loaded = soul_init._load_toml(out_path)
        assert loaded["team"]["name"] == "roundtrip-team"
        assert loaded["team"]["stagger_seconds"] == 15
        assert len(loaded["agents"]) == 1
        assert loaded["agents"][0]["name"] == "agent-a"
        assert loaded["agents"][0]["model"] == "opus"

    def test_save_preserves_booleans(self, tmp_path):
        data = {
            "team": {"name": "bool-test"},
            "policies": {"guardian": True, "idle_shutdown": False},
            "agents": [],
        }
        out_path = tmp_path / "booleans.toml"
        soul_init._save_toml_from_dict(data, out_path)
        loaded = soul_init._load_toml(out_path)
        assert loaded["policies"]["guardian"] is True
        assert loaded["policies"]["idle_shutdown"] is False

    def test_save_preserves_lists(self, tmp_path):
        data = {
            "team": {"name": "list-test"},
            "agents": [],
            "layout": {
                "columns": 2,
                "rows": 1,
                "grid": [{"col": 1, "agents": ["a", "b"]}],
            },
        }
        out_path = tmp_path / "lists.toml"
        soul_init._save_toml_from_dict(data, out_path)
        loaded = soul_init._load_toml(out_path)
        assert loaded["layout"]["grid"][0]["agents"] == ["a", "b"]


# ── Layout recalculation ───────────────────────────────────────────────────

class TestLayoutRecalculation:

    def test_single_agent(self):
        data = {"agents": [{"name": "solo"}]}
        soul_init._recalculate_layout(data)
        assert data["layout"]["columns"] == 2  # CEO + 1
        assert data["layout"]["rows"] == 1
        assert len(data["layout"]["grid"]) == 1

    def test_three_agents_one_column(self):
        data = {"agents": [{"name": f"a{i}"} for i in range(3)]}
        soul_init._recalculate_layout(data)
        assert data["layout"]["columns"] == 2  # CEO + 1
        assert data["layout"]["rows"] == 3

    def test_four_agents_two_columns(self):
        data = {"agents": [{"name": f"a{i}"} for i in range(4)]}
        soul_init._recalculate_layout(data)
        assert data["layout"]["columns"] == 3  # CEO + 2

    def test_seven_agents_three_columns(self):
        data = {"agents": [{"name": f"a{i}"} for i in range(7)]}
        soul_init._recalculate_layout(data)
        assert data["layout"]["columns"] == 4  # CEO + 3

    def test_empty_agents_removes_layout(self):
        data = {"agents": [], "layout": {"columns": 2}}
        soul_init._recalculate_layout(data)
        assert "layout" not in data


# ── Template model defaults ────────────────────────────────────────────────

class TestTemplateModelDefaults:

    def test_developer_defaults_to_sonnet(self):
        assert soul_init._get_template_model_default("developer") == "sonnet"

    def test_strategist_defaults_to_opus(self):
        assert soul_init._get_template_model_default("strategist") == "opus"

    def test_security_defaults_to_opus(self):
        assert soul_init._get_template_model_default("security") == "opus"

    def test_qa_defaults_to_haiku(self):
        assert soul_init._get_template_model_default("qa") == "haiku"

    def test_coach_defaults_to_haiku(self):
        assert soul_init._get_template_model_default("coach") == "haiku"

    def test_unknown_template_defaults_to_sonnet(self):
        assert soul_init._get_template_model_default("nonexistent-template") == "sonnet"

    def test_none_template_defaults_to_sonnet(self):
        assert soul_init._get_template_model_default(None) == "sonnet"


# ── TOML value formatting ──────────────────────────────────────────────────

class TestTomlValueFormatting:

    def test_string(self):
        assert soul_init._toml_value("hello") == '"hello"'

    def test_int(self):
        assert soul_init._toml_value(42) == "42"

    def test_bool_true(self):
        assert soul_init._toml_value(True) == "true"

    def test_bool_false(self):
        assert soul_init._toml_value(False) == "false"

    def test_list(self):
        assert soul_init._toml_value(["a", "b"]) == '["a", "b"]'

    def test_empty_list(self):
        assert soul_init._toml_value([]) == "[]"

    def test_string_with_quotes(self):
        result = soul_init._toml_value('say "hello"')
        assert '\\"' in result


# ── add-agent subcommand ───────────────────────────────────────────────────

class TestAddAgent:

    def test_add_from_template(self, sample_toml, mock_home):
        """Adding from template creates a new agent entry."""
        args = mock.Mock()
        args.template = "developer"
        args.custom = False

        with mock.patch.object(soul_init, "_resolve_config_path", return_value=sample_toml):
            soul_init.cmd_add_agent(args)

        data = soul_init._load_toml(sample_toml)
        names = [a["name"] for a in data["agents"]]
        assert "developer" in names or "developer-2" in names
        assert len(data["agents"]) == 3

    def test_add_avoids_name_collision(self, sample_toml, mock_home):
        """Agent name is deduplicated when template name already exists."""
        # First add a "developer" agent (which will get a unique name since "dev-1" exists)
        data = soul_init._load_toml(sample_toml)
        data["agents"].append({"name": "developer", "model": "sonnet", "machine": "local", "cgroup": True})
        soul_init._save_toml_from_dict(data, sample_toml)

        args = mock.Mock()
        args.template = "developer"
        args.custom = False

        with mock.patch.object(soul_init, "_resolve_config_path", return_value=sample_toml):
            soul_init.cmd_add_agent(args)

        data = soul_init._load_toml(sample_toml)
        names = [a["name"] for a in data["agents"]]
        assert "developer-2" in names

    def test_add_unknown_template_exits(self, sample_toml, mock_home):
        args = mock.Mock()
        args.template = "nonexistent"
        args.custom = False

        with mock.patch.object(soul_init, "_resolve_config_path", return_value=sample_toml):
            with pytest.raises(SystemExit):
                soul_init.cmd_add_agent(args)


# ── remove-agent subcommand ────────────────────────────────────────────────

class TestRemoveAgent:

    def test_remove_existing_agent(self, sample_toml, mock_home):
        args = mock.Mock()
        args.name = "dev-1"

        with mock.patch.object(soul_init, "_resolve_config_path", return_value=sample_toml):
            soul_init.cmd_remove_agent(args)

        data = soul_init._load_toml(sample_toml)
        names = [a["name"] for a in data["agents"]]
        assert "dev-1" not in names
        assert len(data["agents"]) == 1

    def test_remove_nonexistent_exits(self, sample_toml, mock_home):
        args = mock.Mock()
        args.name = "nonexistent"

        with mock.patch.object(soul_init, "_resolve_config_path", return_value=sample_toml):
            with pytest.raises(SystemExit):
                soul_init.cmd_remove_agent(args)

    def test_remove_updates_layout(self, sample_toml, mock_home):
        args = mock.Mock()
        args.name = "dev-1"

        with mock.patch.object(soul_init, "_resolve_config_path", return_value=sample_toml):
            soul_init.cmd_remove_agent(args)

        data = soul_init._load_toml(sample_toml)
        # Layout should be recalculated for 1 agent
        assert data["layout"]["columns"] == 2  # CEO + 1


# ── list-agents subcommand ─────────────────────────────────────────────────

class TestListAgents:

    def test_list_agents_outputs(self, sample_toml, capsys):
        args = mock.Mock()

        with mock.patch.object(soul_init, "_resolve_config_path", return_value=sample_toml):
            soul_init.cmd_list_agents(args)

        output = capsys.readouterr().out
        assert "dev-1" in output
        assert "research-1" in output
        assert "test-team" in output

    def test_list_empty(self, tmp_path, capsys, mock_home):
        toml = tmp_path / "empty.toml"
        toml.write_text('[team]\nname = "empty"\n')

        args = mock.Mock()
        with mock.patch.object(soul_init, "_resolve_config_path", return_value=toml):
            soul_init.cmd_list_agents(args)

        output = capsys.readouterr().out
        assert "No agents configured" in output


# ── config subcommand ──────────────────────────────────────────────────────

class TestConfigCommand:

    def test_config_view(self, sample_toml, capsys):
        args = mock.Mock()
        args.set_value = None

        with mock.patch.object(soul_init, "_resolve_config_path", return_value=sample_toml):
            soul_init.cmd_config(args)

        output = capsys.readouterr().out
        assert "test-team" in output

    def test_config_set_stagger(self, sample_toml):
        args = mock.Mock()
        args.set_value = "stagger_seconds=20"

        with mock.patch.object(soul_init, "_resolve_config_path", return_value=sample_toml):
            soul_init.cmd_config(args)

        data = soul_init._load_toml(sample_toml)
        assert data["team"]["stagger_seconds"] == 20

    def test_config_set_boolean(self, sample_toml):
        args = mock.Mock()
        args.set_value = "guardian=false"

        with mock.patch.object(soul_init, "_resolve_config_path", return_value=sample_toml):
            soul_init.cmd_config(args)

        data = soul_init._load_toml(sample_toml)
        assert data["policies"]["guardian"] is False

    def test_config_set_string(self, sample_toml):
        args = mock.Mock()
        args.set_value = "boot_prompt=Hello world"

        with mock.patch.object(soul_init, "_resolve_config_path", return_value=sample_toml):
            soul_init.cmd_config(args)

        data = soul_init._load_toml(sample_toml)
        assert data["team"]["boot_prompt"] == "Hello world"

    def test_config_set_unknown_key_exits(self, sample_toml):
        args = mock.Mock()
        args.set_value = "unknown_key=value"

        with mock.patch.object(soul_init, "_resolve_config_path", return_value=sample_toml):
            with pytest.raises(SystemExit):
                soul_init.cmd_config(args)


# ── add-machine subcommand ─────────────────────────────────────────────────

class TestAddMachine:

    def test_add_machine(self, sample_toml):
        args = mock.Mock()
        args.name = "worker-1"
        args.ssh = "user@remote"
        args.no_test = True

        with mock.patch.object(soul_init, "_resolve_config_path", return_value=sample_toml):
            soul_init.cmd_add_machine(args)

        data = soul_init._load_toml(sample_toml)
        assert len(data["machines"]) == 1
        assert data["machines"][0]["name"] == "worker-1"
        assert data["machines"][0]["ssh"] == "user@remote"

    def test_add_duplicate_machine_exits(self, sample_toml):
        # First add
        args = mock.Mock()
        args.name = "worker-1"
        args.ssh = "user@remote"
        args.no_test = True

        with mock.patch.object(soul_init, "_resolve_config_path", return_value=sample_toml):
            soul_init.cmd_add_machine(args)

        # Duplicate should fail
        with mock.patch.object(soul_init, "_resolve_config_path", return_value=sample_toml):
            with pytest.raises(SystemExit):
                soul_init.cmd_add_machine(args)


# ── list-machines subcommand ───────────────────────────────────────────────

class TestListMachines:

    def test_list_machines_shows_local(self, sample_toml, capsys):
        args = mock.Mock()

        with mock.patch.object(soul_init, "_resolve_config_path", return_value=sample_toml):
            soul_init.cmd_list_machines(args)

        output = capsys.readouterr().out
        assert "local" in output
        assert "2" in output  # 2 local agents


# ── Available templates ────────────────────────────────────────────────────

class TestAvailableTemplates:

    def test_all_16_templates_registered(self):
        assert len(soul_init.AVAILABLE_TEMPLATES) == 16

    def test_all_templates_have_descriptions(self):
        for t in soul_init.AVAILABLE_TEMPLATES:
            assert t in soul_init.TEMPLATE_DESCRIPTIONS, f"Missing description for {t}"

    def test_all_templates_have_files(self):
        for t in soul_init.AVAILABLE_TEMPLATES:
            path = soul_init.TEMPLATES_DIR / f"{t}.md"
            assert path.exists(), f"Missing template file: {path}"

    def test_all_template_files_have_frontmatter(self):
        for t in soul_init.AVAILABLE_TEMPLATES:
            path = soul_init.TEMPLATES_DIR / f"{t}.md"
            content = path.read_text()
            assert content.startswith("---"), f"Template {t} missing frontmatter"
            assert "model_default:" in content, f"Template {t} missing model_default"
            assert "{{AGENT_NAME}}" in content, f"Template {t} missing {{AGENT_NAME}} placeholder"


# ── State detection ────────────────────────────────────────────────────────

class TestStateDetection:

    def test_first_run_when_no_config(self, mock_home):
        """No config file = first_run state."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SOUL_TEAM_CONFIG", None)
            state, data = soul_init.detect_state()
            assert state == "first_run"
            assert data is None

    def test_configured_when_config_exists_no_session(self, mock_home, sample_toml):
        """Config exists, no tmux session = configured state."""
        # Copy config to mock home
        config_path = mock_home / ".soul-team" / "config.toml"
        config_path.write_text(sample_toml.read_text())

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SOUL_TEAM_CONFIG", None)
            with mock.patch("subprocess.run") as mock_run:
                # tmux has-session returns non-zero (no session)
                mock_run.return_value = mock.Mock(returncode=1)
                state, data = soul_init.detect_state()
                assert state == "configured"
                assert data is not None
                assert data["team"]["name"] == "test-team"

    def test_running_when_session_exists(self, mock_home, sample_toml):
        """Config exists, tmux session running = running state."""
        config_path = mock_home / ".soul-team" / "config.toml"
        config_path.write_text(sample_toml.read_text())

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SOUL_TEAM_CONFIG", None)
            with mock.patch("subprocess.run") as mock_run:
                # tmux has-session returns 0 (session exists)
                mock_run.return_value = mock.Mock(returncode=0)
                state, data = soul_init.detect_state()
                assert state == "running"
                assert data is not None


# ── Interactive menu fallback ──────────────────────────────────────────────

class TestInteractiveMenuFallback:

    def test_raw_mode_check_no_tty(self):
        """_supports_raw_mode returns False when stdin is not a tty."""
        with mock.patch.object(sys, "stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            assert soul_init._supports_raw_mode() is False

    def test_select_menu_fallback_returns_default(self, monkeypatch):
        """Fallback menu returns default when user presses Enter."""
        monkeypatch.setattr("builtins.input", lambda _: "")
        result = soul_init._select_menu_fallback(
            "Pick one:", ["A", "B", "C"], None, 1, False
        )
        assert result == 1

    def test_select_menu_fallback_returns_choice(self, monkeypatch):
        """Fallback menu returns user's numbered choice."""
        monkeypatch.setattr("builtins.input", lambda _: "2")
        result = soul_init._select_menu_fallback(
            "Pick one:", ["A", "B", "C"], None, 0, False
        )
        assert result == 1

    def test_multi_select_fallback_returns_indices(self, monkeypatch):
        """Fallback multi-select returns correct indices."""
        monkeypatch.setattr("builtins.input", lambda _: "1,3")
        result = soul_init._multi_select_fallback(
            "Pick:", ["A", "B", "C"], None
        )
        assert result == [0, 2]


# ── Quick start config ─────────────────────────────────────────────────────

class TestQuickStartConfig:

    def test_quick_start_creates_correct_agents(self):
        config = soul_init._quick_start_config(3)
        assert len(config.agents) == 3
        assert config.agents[0].template == "developer"
        assert config.agents[1].template == "researcher"
        assert config.agents[2].template == "assistant"

    def test_quick_start_wraps_templates(self):
        config = soul_init._quick_start_config(20)
        assert len(config.agents) == 20
        # Templates should rotate
        templates = [a.template for a in config.agents]
        assert templates[0] == "developer"
        assert templates[16] == "developer"


# ── Data models ────────────────────────────────────────────────────────────

class TestDataModels:

    def test_team_config_defaults(self):
        config = soul_init.TeamConfig()
        assert config.team_name == "my-team"
        assert config.stagger_seconds == 10
        assert config.enable_guardian is True
        assert config.agents == []

    def test_agent_defaults(self):
        agent = soul_init.Agent(name="test", role="testing")
        assert agent.model == "sonnet"
        assert agent.machine == "local"
        assert agent.template is None
        assert agent.cgroup is True


# ── TOML generation ────────────────────────────────────────────────────────

class TestTomlGeneration:

    def test_generate_toml_basic(self):
        config = soul_init.TeamConfig()
        config.agents = [soul_init.Agent(name="dev", role="developer", template="developer")]
        toml = soul_init.generate_toml(config)
        assert "[team]" in toml
        assert "[[agents]]" in toml
        assert 'name = "dev"' in toml

    def test_generate_toml_distributed(self):
        config = soul_init.TeamConfig()
        config.machines = [soul_init.Machine(name="worker-1", ssh_target="user@host")]
        config.agents = [
            soul_init.Agent(name="local-dev", role="dev", machine="local"),
            soul_init.Agent(name="remote-dev", role="dev", machine="worker-1"),
        ]
        toml = soul_init.generate_toml(config)
        assert "Local agents" in toml
        assert "Remote agents" in toml


# ── Version constant ───────────────────────────────────────────────────────

class TestVersion:

    def test_version_defined(self):
        assert hasattr(soul_init, "VERSION")
        assert soul_init.VERSION == "2.0.0"
