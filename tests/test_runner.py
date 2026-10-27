"""Tests for runner.py."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from ralph_loop.config import AgentConfig, RalphConfig
from ralph_loop.runner import (
    LoopRunner,
    _tool_call_entry,
    _tool_call_result,
    _tool_call_summary,
)
from ralph_loop.tasks import TasksFile


@pytest.fixture
def sample_tasks_file(tmp_path: Path) -> Path:
    """Create a sample tasks file."""
    tasks_file = tmp_path / "tasks_list.json"
    tasks_data = [
        {
            "category": "test",
            "description": "Task 1",
            "steps": ["Step 1"],
            "passes": False,
        },
        {
            "category": "test",
            "description": "Task 2",
            "steps": ["Step 2"],
            "passes": True,
        },
    ]
    tasks_file.write_text(json.dumps(tasks_data))
    return tasks_file


@pytest.fixture
def config(sample_tasks_file: Path) -> RalphConfig:
    """Create a test configuration."""
    return RalphConfig(
        tasks_file=sample_tasks_file,
        claude=AgentConfig(
            command=["echo"],
            instructions="test instructions",
        ),
    )


def test_loop_runner_init(config: RalphConfig):
    """Test LoopRunner initialization."""
    runner = LoopRunner(config)
    assert runner.config == config
    assert runner.completed == 0


def test_loop_runner_no_tasks_file(config: RalphConfig):
    """Test error when tasks file doesn't exist."""
    config.tasks_file = Path("/nonexistent/tasks.json")
    runner = LoopRunner(config)
    with pytest.raises(FileNotFoundError):
        runner.run("claude", 1)


def test_loop_runner_all_tasks_complete(tmp_path: Path):
    """Test early exit when all tasks are complete."""
    tasks_file = tmp_path / "tasks_list.json"
    tasks_file.write_text(
        json.dumps(
            [
                {
                    "category": "test",
                    "description": "Task",
                    "steps": [],
                    "passes": True,
                }
            ]
        )
    )

    config = RalphConfig(tasks_file=tasks_file)
    runner = LoopRunner(config)

    with patch("ralph_loop.runner.subprocess.run") as mock_run:
        runner.run("claude", None)
        # Should not run any iterations
        mock_run.assert_not_called()


def test_loop_runner_invalid_iterations(config: RalphConfig, sample_tasks_file: Path):
    """Test error with invalid iterations."""
    runner = LoopRunner(config)
    with pytest.raises(ValueError, match="positive integer"):
        runner.run("claude", 0)

    with pytest.raises(ValueError, match="positive integer"):
        runner.run("claude", -1)


@patch("ralph_loop.runner.subprocess.run")
def test_loop_runner_success(mock_run: Mock, config: RalphConfig):
    """Test successful loop execution."""
    mock_run.return_value = Mock(returncode=0)

    runner = LoopRunner(config)
    runner.run("claude", 2)

    assert mock_run.call_count == 2
    assert runner.completed == 2


@patch("ralph_loop.runner.subprocess.run")
def test_loop_runner_default_iterations(mock_run: Mock, config: RalphConfig):
    """Test default iterations equals incomplete task count."""
    mock_run.return_value = Mock(returncode=0)

    runner = LoopRunner(config)
    runner.run("claude", None)

    # Should run once (one incomplete task)
    assert mock_run.call_count == 1


@patch("ralph_loop.runner.subprocess.run")
def test_loop_runner_command_not_found(mock_run: Mock, config: RalphConfig):
    """Test error when agent command is not found."""
    mock_run.side_effect = FileNotFoundError("command not found")

    runner = LoopRunner(config)
    with pytest.raises(RuntimeError, match="Agent command not found"):
        runner.run("claude", 1)


@patch("ralph_loop.runner.subprocess.run")
def test_loop_runner_command_failure(mock_run: Mock, config: RalphConfig):
    """Test error when agent command fails."""
    mock_run.side_effect = subprocess.CalledProcessError(1, "command")

    runner = LoopRunner(config)
    with pytest.raises(RuntimeError, match="Agent command failed"):
        runner.run("claude", 1)


@patch("ralph_loop.runner.subprocess.run")
def test_loop_runner_instructions_passed(mock_run: Mock, config: RalphConfig):
    """Test that instructions are passed to agent command."""
    mock_run.return_value = Mock(returncode=0)

    runner = LoopRunner(config)
    runner.run("claude", 1)

    # Verify command was called with instructions
    call_args = mock_run.call_args
    assert call_args is not None
    command = call_args[0][0]
    assert "test instructions" in command


@patch("ralph_loop.runner.subprocess.Popen")
def test_loop_runner_streaming_mode(
    mock_popen: Mock, config: RalphConfig, sample_tasks_file: Path
):
    """Test streaming mode for cursor-agent."""
    # Setup mock process for streaming
    mock_process = Mock()
    mock_process.stdout = iter(
        [
            '{"type": "system", "subtype": "init", "model": "composer-1"}\n',
            '{"type": "assistant", "message": {"content": [{"text": "test"}]}}\n',
            '{"type": "result", "duration_ms": 1000}\n',
        ]
    )
    mock_process.poll.return_value = None  # Process is running during streaming
    mock_process.wait.return_value = 0
    mock_process.returncode = 0
    mock_popen.return_value = mock_process

    # Configure cursor-agent with streaming
    config.cursor_agent = AgentConfig(
        command=[
            "agent",
            "--output-format",
            "stream-json",
            "--stream-partial-output",
            "-p",
        ],
        instructions="test instructions",
    )

    runner = LoopRunner(config)
    runner.run("cursor-agent", 1)

    # Verify Popen was called (not subprocess.run)
    mock_popen.assert_called_once()
    mock_process.wait.assert_called_once()


def test_parse_stream_json():
    """Test JSON parsing from stream."""
    runner = LoopRunner(RalphConfig())

    # Valid JSON
    result = runner._parse_stream_json('{"type": "test", "value": 123}\n')
    assert result == {"type": "test", "value": 123}

    # Invalid JSON
    result = runner._parse_stream_json("not json\n")
    assert result is None

    # Empty line
    result = runner._parse_stream_json("\n")
    assert result is None


def _streaming_runner(config: RalphConfig) -> LoopRunner:
    """Configure a runner for cursor-agent streaming."""
    config.cursor_agent = AgentConfig(
        command=[
            "agent",
            "--output-format",
            "stream-json",
            "--stream-partial-output",
            "-p",
        ],
        instructions="test instructions",
    )
    return LoopRunner(config)


def _run_streaming(runner: LoopRunner, events: list[dict]) -> None:
    """Run one iteration against the given stream events."""
    lines = [json.dumps(event) + "\n" for event in events]
    with patch("ralph_loop.runner.subprocess.Popen") as mock_popen:
        process = Mock()
        process.stdout = iter(lines)
        process.poll.return_value = None
        process.wait.return_value = 0
        process.returncode = 0
        mock_popen.return_value = process
        runner.run("cursor-agent", 1)


def test_streaming_displays_full_agent_output(config: RalphConfig, capsys):
    """Assistant text, thinking, tools, and results are all shown."""
    _run_streaming(
        _streaming_runner(config),
        [
            {"type": "system", "subtype": "init", "model": "composer-2"},
            {"type": "thinking", "subtype": "delta", "text": "planning", "timestamp_ms": 1},
            {"type": "thinking", "subtype": "completed", "timestamp_ms": 2},
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Hello"}]},
                "timestamp_ms": 3,
            },
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": " world"}]},
                "timestamp_ms": 4,
            },
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Hello world"}]},
            },
            {
                "type": "tool_call",
                "subtype": "started",
                "tool_call": {"shellToolCall": {"args": {"command": "ls -la"}}},
            },
            {
                "type": "tool_call",
                "subtype": "completed",
                "tool_call": {
                    "shellToolCall": {
                        "args": {"command": "ls -la"},
                        "result": {"success": {"exitCode": 0, "stdout": "a\nb\n"}},
                    }
                },
            },
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Done."}]},
            },
            {"type": "result", "duration_ms": 10, "result": "Done."},
        ],
    )

    out = capsys.readouterr().out
    assert out.count("Hello world") == 1  # final flush is not duplicated
    assert "planning" in out
    assert "ls -la" in out
    assert "exit 0, 2 output line(s)" in out
    assert "Done." in out


def test_streaming_skips_buffered_flush_before_tool_call(config: RalphConfig, capsys):
    """The pre-tool-call flush repeats deltas and must be skipped."""
    _run_streaming(
        _streaming_runner(config),
        [
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Hi"}]},
                "timestamp_ms": 1,
            },
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Hi"}]},
                "timestamp_ms": 2,
                "model_call_id": "call-1",
            },
            {
                "type": "tool_call",
                "subtype": "started",
                "tool_call": {"readToolCall": {"args": {"path": "a.py"}}},
            },
            {"type": "result", "duration_ms": 5},
        ],
    )

    out = capsys.readouterr().out
    assert out.count("Hi") == 1
    assert "a.py" in out


def test_streaming_prints_complete_messages_without_partial_output(
    config: RalphConfig, capsys
):
    """Without --stream-partial-output every finished message is shown."""
    _run_streaming(
        _streaming_runner(config),
        [
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "First."}]},
            },
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Second."}]},
            },
            {"type": "result", "duration_ms": 5},
        ],
    )

    out = capsys.readouterr().out
    assert "First." in out
    assert "Second." in out


def test_streaming_shows_non_json_output(config: RalphConfig, capsys):
    """Stderr warnings are not silently dropped."""
    lines = ["⚠ Workspace Trust Required\n"]
    with patch("ralph_loop.runner.subprocess.Popen") as mock_popen:
        process = Mock()
        process.stdout = iter(lines)
        process.poll.return_value = None
        process.wait.return_value = 0
        process.returncode = 0
        mock_popen.return_value = process
        _streaming_runner(config).run("cursor-agent", 1)

    assert "Workspace Trust Required" in capsys.readouterr().out


def test_tool_call_helpers():
    """Tool call shapes used by the Cursor CLI are summarized."""
    name, payload = _tool_call_entry(
        {
            "editToolCall": {
                "args": {"path": "x.py"},
                "result": {"success": {"linesAdded": 2, "linesRemoved": 1}},
            }
        }
    )
    assert name == "edit"
    assert _tool_call_summary(payload) == "x.py"
    assert _tool_call_result(payload) == "edited (+2/-1 lines)"

    name, payload = _tool_call_entry(
        {"shellToolCall": {"args": {"command": "ls"}, "result": {"rejected": {"reason": "denied"}}}}
    )
    assert name == "shell"
    assert _tool_call_result(payload) == "rejected (denied)"

    name, payload = _tool_call_entry(
        {
            "grepToolCall": {
                "args": {"pattern": "foo"},
                "result": {
                    "success": {"workspaceResults": {".": {"content": {"totalMatchedLines": 3}}}}
                },
            }
        }
    )
    assert name == "grep"
    assert _tool_call_summary(payload) == "foo"
    assert _tool_call_result(payload) == "3 match(es)"

    name, payload = _tool_call_entry(
        {"function": {"name": "web", "arguments": '{"url": "https://x"}'}}
    )
    assert name == "web"
    assert _tool_call_summary(payload) == "https://x"
