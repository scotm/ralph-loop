"""Configuration management for ralph-loop."""

import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

CONFIG_VERSION = 1

AGENT_NAMES = ("claude", "cursor-agent", "opencode")
AgentName = Literal["claude", "cursor-agent", "opencode"]

DEFAULT_INSTRUCTIONS = """Initial tasks

  - Run `pwd` to see the working directory. Work only inside this repository and do not modify files outside it.
  - Read `AGENTS.md` or `CLAUDE.md` in the repository root if present, recent git history (`git log --oneline -20`), and `{progress_file}` to get up to speed on what was recently worked on.
  - Read the `{tasks_file}` task list and choose the first task whose `passes` field is false. Do not work on multiple tasks at once.

  Then, work on that task only.

  Before marking it complete, run the project's tests (and linter if configured) and make sure they pass.

  Once it passes, update only that task's `passes` property to true. If you cannot finish it, leave `passes` false and record the blocker in `{progress_file}`.

  Update `{progress_file}` with a 3-4 line summary of what has been done. Be extremely concise. Sacrifice grammar for the sake of concision.

  IT IS IMPERATIVE THAT YOU DO NOT UPDATE `{tasks_file}` IN ANY OTHER WAY - only the single task `passes` property. Do not remove or edit other fields; doing so could break the loop.

  If you learn anything useful for future turns - such as implementation details or test-writing guidance - update `AGENTS.md` (or `CLAUDE.md` if that is the file that exists).

  Then commit these changes, other than files in `{state_dir}`. Report on how you did."""


class AgentConfig(BaseModel):
    """Configuration for a single agent."""

    command: list[str] = Field(description="Command and arguments to run the agent")
    instructions: str = Field(description="Instructions to pass to the agent")
    streaming: bool = Field(
        default=False,
        description="Parse agent output as stream-json events",
    )


class RalphConfig(BaseSettings):
    """Main configuration for ralph-loop."""

    model_config = SettingsConfigDict(
        env_prefix="RALPH_",
        case_sensitive=False,
        extra="ignore",
    )

    tasks_file: Path = Field(
        default=Path(".ralph/tasks_list.json"),
        description="Path to tasks_list.json file",
    )
    progress_file: Path = Field(
        default=Path(".ralph/progress_tasks.txt"),
        description="Path to progress_tasks.txt file",
    )
    config_file: Path = Field(
        default=Path(".ralph/ralph_config.json"),
        description="Path to save/load configuration",
    )
    config_version: int = Field(
        default=CONFIG_VERSION,
        description="Configuration schema version",
    )

    # Agent configurations
    claude: AgentConfig = Field(
        default=AgentConfig(
            command=["claude", "--dangerously-skip-permissions", "-p"],
            instructions=DEFAULT_INSTRUCTIONS,
        ),
    )

    cursor_agent: AgentConfig = Field(
        default=AgentConfig(
            command=[
                "agent",
                "--sandbox",
                "disabled",
                "--force",
                "-p",
                "--output-format",
                "stream-json",
                "--stream-partial-output",
            ],
            instructions=DEFAULT_INSTRUCTIONS,
            streaming=True,
        ),
    )

    opencode: AgentConfig = Field(
        default=AgentConfig(
            command=["opencode", "run"],
            instructions=DEFAULT_INSTRUCTIONS,
        ),
    )

    def get_agent_config(self, agent: AgentName) -> AgentConfig:
        """Get configuration for a specific agent."""
        agent_map = {
            "claude": self.claude,
            "cursor-agent": self.cursor_agent,
            "opencode": self.opencode,
        }
        return agent_map[agent]

    def save(self, path: Path | None = None) -> None:
        """Save configuration to JSON file."""
        save_path = path or self.config_file
        save_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict, handling Path objects
        config_dict = self.model_dump(mode="json")
        # Convert Path objects to strings for JSON serialization
        config_dict["tasks_file"] = str(config_dict["tasks_file"])
        config_dict["progress_file"] = str(config_dict["progress_file"])
        config_dict["config_file"] = str(config_dict["config_file"])

        with save_path.open("w") as f:
            json.dump(config_dict, f, indent=2)

    @classmethod
    def load(cls, path: Path | None = None) -> "RalphConfig":
        """Load configuration from JSON file.

        An explicitly supplied path must exist. The implicit default path falls
        back to built-in defaults when missing.
        """
        explicit = path is not None
        load_path = Path(path) if explicit else Path(cls.model_fields["config_file"].default)
        if not load_path.exists():
            if explicit:
                raise FileNotFoundError(f"Config file not found: {load_path}")
            return cls()

        with load_path.open() as f:
            config_dict = json.load(f)

        cls._check_unknown_keys(config_dict, load_path)

        if config_dict.get("config_version", 0) < CONFIG_VERSION:
            print(
                f"Warning: {load_path} was created by an older ralph-loop. "
                "Run 'ralph-loop config --recreate' to pick up updated defaults.",
                file=sys.stderr,
            )

        # Convert string paths back to Path objects
        for key in ["tasks_file", "progress_file", "config_file"]:
            if key in config_dict:
                config_dict[key] = Path(config_dict[key])

        config = cls(**config_dict)
        config.config_file = load_path
        return config

    @classmethod
    def _check_unknown_keys(cls, config_dict: dict, path: Path) -> None:
        """Reject unknown keys instead of silently ignoring configuration typos."""
        unknown = {key for key in config_dict if key not in cls.model_fields}
        for agent in AGENT_NAMES:
            section = config_dict.get(agent.replace("-", "_"))
            if isinstance(section, dict):
                unknown |= {
                    f"{agent}.{key}" for key in section if key not in AgentConfig.model_fields
                }
        if unknown:
            raise ValueError(
                f"Unknown configuration key(s) in {path}: {', '.join(sorted(unknown))}"
            )


def get_config(config_path: Path | None = None) -> RalphConfig:
    """Get configuration, loading from file if it exists, otherwise using defaults."""
    return RalphConfig.load(config_path)
