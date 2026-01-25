"""Tests for cli.py."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import typer
from typer.testing import CliRunner

from ralph_loop.cli import app, validate_agent

runner = CliRunner()


def test_validate_agent():
    """Test agent validation."""
    assert validate_agent("claude") == "claude"
    assert validate_agent("cursor-agent") == "cursor-agent"
    assert validate_agent("opencode") == "opencode"

    with pytest.raises(typer.BadParameter):
        validate_agent("invalid")


@patch("ralph_loop.cli.LoopRunner")
@patch("ralph_loop.cli.get_config")
def test_run_command_success(mock_get_config: Mock, mock_runner_class: Mock):
    """Test successful run command."""
    mock_config = Mock()
    mock_get_config.return_value = mock_config
    mock_runner = Mock()
    mock_runner_class.return_value = mock_runner

    result = runner.invoke(app, ["run", "claude", "--iterations", "2"])

    assert result.exit_code == 0
    mock_get_config.assert_called_once()
    mock_runner_class.assert_called_once_with(mock_config)
    mock_runner.run.assert_called_once_with("claude", 2)


@patch("ralph_loop.cli.get_config")
def test_run_command_invalid_agent(mock_get_config: Mock):
    """Test run command with invalid agent."""
    mock_get_config.return_value = Mock()

    result = runner.invoke(app, ["run", "invalid-agent"])

    assert result.exit_code == 1
    assert "Agent must be one of" in result.output


@patch("ralph_loop.cli.get_config")
def test_run_command_invalid_iterations(mock_get_config: Mock):
    """Test run command with invalid iterations."""
    mock_get_config.return_value = Mock()

    result = runner.invoke(app, ["run", "claude", "--iterations", "0"])

    assert result.exit_code == 1
    assert "iterations must be a positive integer" in result.output


@patch("ralph_loop.cli.RalphConfig")
def test_config_command_recreate(mock_config_class: Mock):
    """Test config command with --recreate."""
    mock_config = Mock()
    mock_config_class.return_value = mock_config

    result = runner.invoke(app, ["config", "--recreate"])

    assert result.exit_code == 0
    assert "Configuration file created" in result.output
    mock_config.save.assert_called_once()


@patch("ralph_loop.cli.Path")
def test_config_command_show(mock_path_class: Mock):
    """Test config command without --recreate."""
    mock_path = Mock()
    mock_path.exists.return_value = True
    mock_path_class.return_value = mock_path

    result = runner.invoke(app, ["config"])

    assert result.exit_code == 0
    assert "Configuration file exists" in result.output
