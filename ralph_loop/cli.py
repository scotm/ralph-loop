"""CLI interface for ralph-loop."""

import sys
from pathlib import Path
from typing import Literal

import typer
from typer import Option

from ralph_loop.config import RalphConfig, get_config
from ralph_loop.runner import LoopRunner

app = typer.Typer(
    name="ralph-loop",
    help="CLI utility for running AI agent loops on task queues",
    add_completion=False,
)


def validate_agent(agent: str) -> Literal["claude", "cursor-agent", "opencode"]:
    """Validate agent name."""
    valid_agents = ["claude", "cursor-agent", "opencode"]
    if agent not in valid_agents:
        raise typer.BadParameter(f"Agent must be one of: {', '.join(valid_agents)}")
    return agent  # type: ignore


@app.command()
def run(
    agent: str = typer.Argument(..., help="Agent to run: claude, cursor-agent, or opencode"),
    iterations: int | None = Option(
        None,
        "--iterations",
        "-n",
        help="Number of iterations to run (defaults to number of incomplete tasks)",
    ),
    config: Path | None = Option(
        None,
        "--config",
        help="Path to configuration file (defaults to .ralph/ralph_config.json)",
    ),
) -> None:
    """Run the agent loop for specified iterations."""
    # Validate agent
    validated_agent = validate_agent(agent)

    # Validate iterations if provided
    if iterations is not None and iterations <= 0:
        typer.echo("Error: iterations must be a positive integer", err=True)
        raise typer.Exit(1)

    # Load configuration
    try:
        cfg = get_config(config)
    except Exception as e:
        typer.echo(f"Error loading configuration: {e}", err=True)
        raise typer.Exit(1) from e

    # Run the loop
    runner = LoopRunner(cfg)
    try:
        runner.run(validated_agent, iterations)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e
    except RuntimeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e
    except KeyboardInterrupt:
        # Signal handler already printed message and exited
        sys.exit(130)


@app.command()
def config(
    recreate: bool = Option(
        False,
        "--recreate",
        help="Recreate configuration file with default values",
    ),
    config_path: Path | None = Option(
        None,
        "--config",
        help="Path to configuration file (defaults to .ralph/ralph_config.json)",
    ),
) -> None:
    """Manage configuration file."""
    cfg_path = config_path or Path(".ralph/ralph_config.json")

    if recreate:
        # Create default configuration
        cfg = RalphConfig()
        cfg.save(cfg_path)
        typer.echo(f"Configuration file created at: {cfg_path}")
        typer.echo("\nYou can edit this file to customize agent commands and instructions.")
    else:
        # Show current configuration
        if cfg_path.exists():
            typer.echo(f"Configuration file exists at: {cfg_path}")
            typer.echo("\nTo recreate with defaults, run: ralph-loop config --recreate")
        else:
            typer.echo(f"Configuration file not found at: {cfg_path}")
            typer.echo("\nTo create it, run: ralph-loop config --recreate")


if __name__ == "__main__":
    app()
