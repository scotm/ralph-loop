"""Tests for config.py."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from ralph_loop.config import AgentConfig, RalphConfig, get_config


def test_agent_config():
    """Test AgentConfig model."""
    config = AgentConfig(
        command=["test", "command"],
        instructions="Test instructions",
    )
    assert config.command == ["test", "command"]
    assert config.instructions == "Test instructions"


def test_ralph_config_defaults():
    """Test RalphConfig with default values."""
    config = RalphConfig()
    assert config.tasks_file == Path(".ralph/tasks_list.json")
    assert config.claude.command[0] == "claude"
    assert config.cursor_agent.command[0] == "agent"
    assert config.opencode.command[0] == "opencode"


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


def test_get_config_with_existing_file(tmp_path: Path):
    """Test get_config with existing config file."""
    config_file = tmp_path / "ralph_config.json"
    config = RalphConfig(config_file=config_file, tasks_file=tmp_path / "tasks.json")
    config.save()

    loaded = get_config(config_file)
    assert loaded.tasks_file == tmp_path / "tasks.json"


def test_get_config_without_file():
    """Test get_config without existing config file."""
    # Use a non-existent path
    config_file = Path("/tmp/nonexistent_ralph_config.json")
    if config_file.exists():
        config_file.unlink()

    config = get_config(config_file)
    # Should return defaults
    assert config.tasks_file == Path(".ralph/tasks_list.json")
