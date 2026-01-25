# AGENTS.md - Guidelines for AI Coding Agents

This document provides guidelines for AI coding agents working on the ralph-loop project.

## Project Overview

Ralph-loop is a CLI utility for running AI agent loops (Opencode, Claude, and Cursor) to work through task queues defined in `tasks_list.json`. Built with Python 3.14+, typer for CLI, and pydantic for configuration.

## Build, Lint, and Test Commands

### Installation
```bash
# Standard installation to ~/.local/bin
uv pip install --prefix ~/.local -e .

# With development dependencies
uv pip install --prefix ~/.local -e ".[dev]"
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=ralph_loop --cov-report=term-missing

# Run a single test file
pytest tests/test_cli.py

# Run a single test class
pytest tests/test_cli.py::test_run_command_success

# Run a single test function
pytest tests/test_cli.py::test_validate_agent
```

### Code Quality
```bash
# Type checking (if mypy is added)
mypy ralph_loop tests

# Format checking (if ruff/black is added)
ruff check ralph_loop tests
```

## Code Style Guidelines

### Imports
Organize imports in three sections with blank lines between:
1. Standard library imports (sys, pathlib, json, etc.)
2. Third-party imports (typer, pydantic, pytest, etc.)
3. Local application imports (ralph_loop.*)

```python
"""Module docstring."""

import sys
from pathlib import Path
from typing import Literal

import typer
from typer import Option

from ralph_loop.config import RalphConfig, get_config
from ralph_loop.runner import LoopRunner
```

### Naming Conventions
- **Modules/Files**: snake_case (`cli.py`, `test_runner.py`)
- **Classes**: PascalCase (`RalphConfig`, `AgentConfig`)
- **Functions/Variables**: snake_case (`get_config`, `validated_agent`)
- **Constants**: UPPER_SNAKE_CASE (define at module level)
- **Type Variables**: PascalCase (per typing conventions)

### Type Hints
- Use type hints for all function parameters and return types
- Use `T | None` for optional types (Python 3.10+)
- Use `Literal` for string literal unions
- Use `Path` from pathlib for file paths, not strings

```python
def run(
    agent: str = typer.Argument(..., help="Agent to run: claude, cursor-agent, or opencode"),
    iterations: int | None = Option(None, "--iterations", "-n"),
    config: Path | None = Option(None, "--config"),
) -> None:
```

### Docstrings
Use triple-quoted docstrings for all public modules, classes, and functions. Use Google-style docstrings:

```python
def get_config(config_path: Path | None = None) -> RalphConfig:
    """Get configuration, loading from file if it exists, otherwise using defaults."""
    ...
```

### Error Handling
- Use exception chaining (`from e` or `from None`)
- Handle specific exceptions before general ones
- Use typer's `BadParameter` for CLI validation errors
- Return exit codes with `typer.Exit(1)` on errors
- Never suppress errors with bare `except:` or `except Exception:`

```python
try:
    cfg = get_config(config)
except Exception as e:
    typer.echo(f"Error loading configuration: {e}", err=True)
    raise typer.Exit(1) from e
```

### Pydantic Models
- Inherit from `BaseModel` for data models
- Use `Field` with `description` for configuration fields
- Use `BaseSettings` for settings/config classes
- Configure with `SettingsConfigDict` for env vars

```python
class AgentConfig(BaseModel):
    """Configuration for a single agent."""

    command: list[str] = Field(description="Command and arguments to run the agent")
    instructions: str = Field(description="Instructions to pass to the agent")
```

### CLI Commands with Typer
- Use `@app.command()` decorator
- Use `typer.Argument` and `typer.Option` for parameters
- Add help text to all parameters
- Validate inputs early with clear error messages

### Testing Patterns
- Use `pytest` for all tests
- Name test files: `test_*.py`
- Name test classes: `Test*`
- Name test functions: `test_*`
- Use `unittest.mock.patch` for mocking dependencies
- Use `typer.testing.CliRunner` for CLI testing
- Test both success and error paths

```python
@patch("ralph_loop.cli.LoopRunner")
@patch("ralph_loop.cli.get_config")
def test_run_command_success(mock_get_config: Mock, mock_runner_class: Mock):
    """Test successful run command."""
    ...
```

## Task Workflow

When working on tasks from `tasks_list.json`:
1. Read `CLAUDE.md`, git logs, and `progress_tasks.txt` for context
2. Pick the highest-priority incomplete task
3. Complete the task before moving to another
4. Only update the `passes` field of completed tasks
5. Add 3-4 line summary to `progress_tasks.txt`
6. Commit changes (excluding `.ralph/` directory files)

## Architecture Notes

- `ralph_loop/cli.py`: Typer CLI app with run and config commands
- `ralph_loop/config.py`: Pydantic settings and configuration management
- `ralph_loop/runner.py`: Loop execution logic
- `ralph_loop/tasks.py`: Task queue management
- `tests/`: Corresponding test files for each module
