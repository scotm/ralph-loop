"""Tests for config.py."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from ralph_loop.config import DEFAULT_INSTRUCTIONS, AgentConfig, RalphConfig, get_config


def test_agent_config():
    """Test AgentConfig model."""
    config = AgentConfig(
        command=["test", "command"],
        instructions="Test instructions",
    )
    assert config.command == ["test", "command"]
    assert config.instructions == "Test instructions"


def test_default_instructions_shared_by_all_agents():
    """All agents use the same templated instructions."""
    config = RalphConfig()
    assert config.claude.instructions == DEFAULT_INSTRUCTIONS
    assert config.cursor_agent.instructions == DEFAULT_INSTRUCTIONS
    assert config.opencode.instructions == DEFAULT_INSTRUCTIONS

    for placeholder in ("{tasks_file}", "{progress_file}", "{state_dir}"):
        assert placeholder in DEFAULT_INSTRUCTIONS

    # Paths come from config at run time, not from hardcoded strings.
    assert "ralph/progress_tasks.txt" not in DEFAULT_INSTRUCTIONS
    assert "AGENTS.md" in DEFAULT_INSTRUCTIONS
    assert "passes" in DEFAULT_INSTRUCTIONS
    assert "blocker" in DEFAULT_INSTRUCTIONS


def test_ralph_config_defaults():
    """Test RalphConfig with default values."""
    config = RalphConfig()
    assert config.tasks_file == Path(".ralph/tasks_list.json")
    assert config.claude.command[0] == "claude"
    assert config.cursor_agent.command[0] == "agent"
    assert config.opencode.command[0] == "opencode"
    assert config.config_version == 1


def test_default_commands_do_not_pin_models():
    """Each CLI picks its own default model, so model retirements cannot break the loop."""
    config = RalphConfig()
    for agent_config in (config.claude, config.cursor_agent, config.opencode):
        assert "--model" not in agent_config.command


def test_streaming_is_configured_per_agent():
    """Streaming output is a config flag, not a command substring or agent name."""
    config = RalphConfig()
    assert config.cursor_agent.streaming is True
    assert config.claude.streaming is False
    assert config.opencode.streaming is False


def test_get_agent_config():
    """Test getting agent configuration."""
    config = RalphConfig()
    claude_config = config.get_agent_config("claude")
    assert claude_config.command[0] == "claude"

    cursor_config = config.get_agent_config("cursor-agent")
    assert cursor_config.command[0] == "agent"

    opencode_config = config.get_agent_config("opencode")
    assert opencode_config.command[0] == "opencode"


def test_save_and_load_config(tmp_path: Path):
    """Test saving and loading configuration."""
    config_file = tmp_path / "config.json"
    config = RalphConfig(config_file=config_file)
    config.tasks_file = tmp_path / "custom_tasks.json"

    # Save
    config.save()

    # Verify file exists
    assert config_file.exists()

    # Load
    loaded = RalphConfig.load(config_file)
    assert loaded.tasks_file == tmp_path / "custom_tasks.json"
    assert loaded.claude.command[0] == "claude"
    assert loaded.config_file == config_file


def test_get_config_with_existing_file(tmp_path: Path):
    """Test get_config with existing config file."""
    config_file = tmp_path / "ralph_config.json"
    config = RalphConfig(config_file=config_file, tasks_file=tmp_path / "tasks.json")
    config.save()

    loaded = get_config(config_file)
    assert loaded.tasks_file == tmp_path / "tasks.json"
    assert loaded.config_file == config_file


def test_get_config_explicit_missing_file_raises(tmp_path: Path):
    """An explicit --config typo must fail instead of silently using defaults."""
    missing = tmp_path / "typo.json"

    with pytest.raises(FileNotFoundError, match=str(missing)):
        get_config(missing)


def test_get_config_implicit_missing_file_uses_defaults(tmp_path: Path, monkeypatch):
    """The default config location is optional."""
    monkeypatch.chdir(tmp_path)

    config = get_config()
    assert config.tasks_file == Path(".ralph/tasks_list.json")


def test_load_rejects_unknown_keys(tmp_path: Path):
    """Misspelled config keys are reported instead of ignored."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"task_file": "typo.json"}))

    with pytest.raises(ValueError, match="task_file"):
        RalphConfig.load(config_file)


def test_load_rejects_unknown_agent_keys(tmp_path: Path):
    """Unknown keys inside an agent section are also reported."""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"claude": {"command": ["claude"], "instructions": "hi", "comand": []}})
    )

    with pytest.raises(ValueError, match="claude.comand"):
        RalphConfig.load(config_file)


def test_load_warns_on_older_config(tmp_path: Path, capsys):
    """A config without a schema version warns that defaults may be stale."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"tasks_file": ".ralph/tasks_list.json"}))

    RalphConfig.load(config_file)

    assert "config --recreate" in capsys.readouterr().err
