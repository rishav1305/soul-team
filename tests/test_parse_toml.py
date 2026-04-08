"""
Tests for ops/parse_toml.py — TOML config parser.

Covers:
  - main() with no args → exit 1
  - main() with missing file → exit 1, error to stderr
  - main() with invalid TOML → exit 1, error to stderr
  - main() with valid minimal config → correct JSON on stdout
  - main() with full config → agents list, agent_machines, stagger_seconds
  - main() with agents missing name → filtered out
  - main() with missing team section → uses defaults

Run: pytest tests/test_parse_toml.py -v
"""

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

# Add repo root to path so we can import ops.parse_toml
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ops.parse_toml import main


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def minimal_toml(tmp_path):
    """Minimal valid TOML with one agent."""
    f = tmp_path / "config.toml"
    f.write_bytes(b"""
[team]
boot_prompt = "hello world"
stagger_seconds = 5

[[agents]]
name = "pepper"
model = "sonnet"
machine = "local"
""")
    return f


@pytest.fixture
def full_toml(tmp_path):
    """Full TOML with multiple agents, machines, and models."""
    f = tmp_path / "config.toml"
    f.write_bytes(b"""
[team]
name = "soul-team"
boot_prompt = "Run your daily routine."
stagger_seconds = 15

[[agents]]
name = "pepper"
model = "sonnet"
machine = "local"

[[agents]]
name = "shuri"
model = "opus"
machine = "worker"

[[agents]]
name = "happy"
model = "haiku"
machine = "local"
""")
    return f


@pytest.fixture
def toml_missing_names(tmp_path):
    """TOML where some agents have no name — those must be filtered out."""
    f = tmp_path / "config.toml"
    f.write_bytes(b"""
[team]
stagger_seconds = 10

[[agents]]
name = "pepper"

[[agents]]
model = "sonnet"

[[agents]]
name = ""
""")
    return f


# ── TestMainNoArgs ────────────────────────────────────────────────────────────


class TestMainNoArgs:
    """main() with no sys.argv arguments."""

    def test_exits_with_code_1(self):
        with patch("sys.argv", ["parse_toml.py"]):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 1

    def test_prints_usage_to_stderr(self, capsys):
        with patch("sys.argv", ["parse_toml.py"]):
            with pytest.raises(SystemExit):
                main()
        captured = capsys.readouterr()
        assert "Usage" in captured.err


# ── TestMainMissingFile ───────────────────────────────────────────────────────


class TestMainMissingFile:
    """main() when the file path does not exist."""

    def test_exits_with_code_1(self, tmp_path):
        missing = str(tmp_path / "nonexistent.toml")
        with patch("sys.argv", ["parse_toml.py", missing]):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 1

    def test_prints_error_to_stderr(self, tmp_path, capsys):
        missing = str(tmp_path / "nonexistent.toml")
        with patch("sys.argv", ["parse_toml.py", missing]):
            with pytest.raises(SystemExit):
                main()
        captured = capsys.readouterr()
        assert "not found" in captured.err or "Error" in captured.err


# ── TestMainInvalidToml ───────────────────────────────────────────────────────


class TestMainInvalidToml:
    """main() with malformed TOML content."""

    def test_exits_with_code_1(self, tmp_path):
        bad = tmp_path / "bad.toml"
        bad.write_bytes(b"this is not [valid toml {{{{")
        with patch("sys.argv", ["parse_toml.py", str(bad)]):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 1

    def test_prints_error_to_stderr(self, tmp_path, capsys):
        bad = tmp_path / "bad.toml"
        bad.write_bytes(b"[broken = garbage")
        with patch("sys.argv", ["parse_toml.py", str(bad)]):
            with pytest.raises(SystemExit):
                main()
        captured = capsys.readouterr()
        assert "Error" in captured.err or "invalid" in captured.err.lower()


# ── TestMainValidMinimal ──────────────────────────────────────────────────────


class TestMainValidMinimal:
    """main() with minimal valid TOML."""

    def _run(self, toml_path, capsys):
        with patch("sys.argv", ["parse_toml.py", str(toml_path)]):
            main()
        return json.loads(capsys.readouterr().out)

    def test_exits_cleanly(self, minimal_toml, capsys):
        with patch("sys.argv", ["parse_toml.py", str(minimal_toml)]):
            main()  # must not raise

    def test_outputs_valid_json(self, minimal_toml, capsys):
        result = self._run(minimal_toml, capsys)
        assert isinstance(result, dict)

    def test_boot_prompt_correct(self, minimal_toml, capsys):
        result = self._run(minimal_toml, capsys)
        assert result["boot_prompt"] == "hello world"

    def test_stagger_seconds_correct(self, minimal_toml, capsys):
        result = self._run(minimal_toml, capsys)
        assert result["stagger_seconds"] == 5

    def test_agents_list_correct(self, minimal_toml, capsys):
        result = self._run(minimal_toml, capsys)
        assert len(result["agents"]) == 1
        assert result["agents"][0]["name"] == "pepper"

    def test_agent_machines_correct(self, minimal_toml, capsys):
        result = self._run(minimal_toml, capsys)
        assert result["agent_machines"]["pepper"] == "local"


# ── TestMainFullConfig ────────────────────────────────────────────────────────


class TestMainFullConfig:
    """main() with multi-agent config including different machines and models."""

    def _run(self, toml_path, capsys):
        with patch("sys.argv", ["parse_toml.py", str(toml_path)]):
            main()
        return json.loads(capsys.readouterr().out)

    def test_all_three_agents_present(self, full_toml, capsys):
        result = self._run(full_toml, capsys)
        names = [a["name"] for a in result["agents"]]
        assert set(names) == {"pepper", "shuri", "happy"}

    def test_agent_models_correct(self, full_toml, capsys):
        result = self._run(full_toml, capsys)
        models = {a["name"]: a["model"] for a in result["agents"]}
        assert models["shuri"] == "opus"
        assert models["pepper"] == "sonnet"
        assert models["happy"] == "haiku"

    def test_agent_machines_map(self, full_toml, capsys):
        result = self._run(full_toml, capsys)
        assert result["agent_machines"]["shuri"] == "worker"
        assert result["agent_machines"]["pepper"] == "local"

    def test_stagger_seconds_15(self, full_toml, capsys):
        result = self._run(full_toml, capsys)
        assert result["stagger_seconds"] == 15


# ── TestMainFilteredAgents ────────────────────────────────────────────────────


class TestMainFilteredAgents:
    """Agents without a name field must be filtered from output."""

    def test_nameless_agents_excluded(self, toml_missing_names, capsys):
        with patch("sys.argv", ["parse_toml.py", str(toml_missing_names)]):
            main()
        result = json.loads(capsys.readouterr().out)
        # Only "pepper" has a valid non-empty name
        assert len(result["agents"]) == 1
        assert result["agents"][0]["name"] == "pepper"

    def test_agent_machines_excludes_nameless(self, toml_missing_names, capsys):
        with patch("sys.argv", ["parse_toml.py", str(toml_missing_names)]):
            main()
        result = json.loads(capsys.readouterr().out)
        assert "pepper" in result["agent_machines"]
        # No empty-string key
        assert "" not in result["agent_machines"]


# ── TestMainDefaults ──────────────────────────────────────────────────────────


class TestMainDefaults:
    """Defaults applied when optional fields are absent."""

    def test_default_stagger_seconds_is_10(self, tmp_path, capsys):
        """Missing stagger_seconds defaults to 10."""
        f = tmp_path / "c.toml"
        f.write_bytes(b"[team]\n[[agents]]\nname = 'x'\n")
        with patch("sys.argv", ["parse_toml.py", str(f)]):
            main()
        result = json.loads(capsys.readouterr().out)
        assert result["stagger_seconds"] == 10

    def test_default_model_is_sonnet(self, tmp_path, capsys):
        """Agent missing model defaults to 'sonnet'."""
        f = tmp_path / "c.toml"
        f.write_bytes(b"[[agents]]\nname = 'x'\n")
        with patch("sys.argv", ["parse_toml.py", str(f)]):
            main()
        result = json.loads(capsys.readouterr().out)
        assert result["agents"][0]["model"] == "sonnet"

    def test_default_machine_is_local(self, tmp_path, capsys):
        """Agent missing machine defaults to 'local'."""
        f = tmp_path / "c.toml"
        f.write_bytes(b"[[agents]]\nname = 'x'\n")
        with patch("sys.argv", ["parse_toml.py", str(f)]):
            main()
        result = json.loads(capsys.readouterr().out)
        assert result["agents"][0]["machine"] == "local"

    def test_empty_boot_prompt_when_team_missing(self, tmp_path, capsys):
        """No [team] section → boot_prompt is empty string."""
        f = tmp_path / "c.toml"
        f.write_bytes(b"[[agents]]\nname = 'x'\n")
        with patch("sys.argv", ["parse_toml.py", str(f)]):
            main()
        result = json.loads(capsys.readouterr().out)
        assert result["boot_prompt"] == ""
