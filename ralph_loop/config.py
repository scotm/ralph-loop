"""Configuration management for ralph-loop."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseModel):
    """Configuration for a single agent."""

    command: list[str] = Field(description="Command and arguments to run the agent")
    instructions: str = Field(description="Instructions to pass to the agent")


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

    # Agent configurations
    claude: AgentConfig = Field(
        default=AgentConfig(
            command=["claude", "--dangerously-skip-permissions", "--model", "opus", "-p"],
            instructions="""Initial tasks

  - Run `pwd` to see the directory you are working in. You will only be able to edit files in this directory.
  - Read @CLAUDE.md in the repository root, the git logs and @./ralph/progress_tasks.txt to get up to speed on what was recently worked on.
  - Read the @.ralph/tasks_list.json list file and choose the single highest-priority feature that is not yet done to work on.
  - Do not work on multiple features at once.

  Then, work on that feature only.

  Once complete, you may update that single feature object "passes" property to true.

  Update `./.ralph/progress_tasks.txt` with a 3-4 lines summary of what has been done. Be extremely concise. Sacrifice grammar for the sake of concision.

  IT IS IMPERATIVE THAT YOU DO NOT UPDATE `./.ralph/tasks_list.json` in any other way - only the single feature "passes" property. It is unacceptable to remove or edit other fields because this could lead to missing or buggy functionality.
  
  If you learn anything useful that might be helpful for future turns - such as implementation or details about writing or updating test cases, please update @CLAUDE.md with this information.

  Then commit these changes, other than the files in the .ralph directory. And report on how you did.""",
        ),
    )

    cursor_agent: AgentConfig = Field(
        default=AgentConfig(
            command=[
                "agent",
                "--model",
                "composer-1.5",
                "--sandbox",
                "disabled",
                "--force",
                "-p",
                "--output-format",
                "stream-json",
                "--stream-partial-output",
            ],
            instructions="""Initial tasks

  - Run `pwd` to see the directory you are working in. You will only be able to edit files in this directory.
  - Read @CLAUDE.md in the repository root, the git logs and @./ralph/progress_tasks.txt to get up to speed on what was recently worked on.
  - Read the @.ralph/tasks_list.json list file and choose the single highest-priority feature that is not yet done to work on.
  - Do not work on multiple features at once.

  Then, work on that feature only.

  Once complete, you may update that single feature object "passes" property to true.

  Update `./.ralph/progress_tasks.txt` with a 3-4 lines summary of what has been done. Be extremely concise. Sacrifice grammar for the sake of concision.

  IT IS IMPERATIVE THAT YOU DO NOT UPDATE `./.ralph/tasks_list.json` in any other way - only the single feature "passes" property. It is unacceptable to remove or edit other fields because this could lead to missing or buggy functionality.
  
  If you learn anything useful that might be helpful for future turns - such as implementation or details about writing or updating test cases, please update @CLAUDE.md with this information.

  Then commit these changes, other than the files in the .ralph directory. And report on how you did.""",
        ),
    )

    opencode: AgentConfig = Field(
        default=AgentConfig(
            command=["opencode", "--model", "openai/gpt-5.1-codex-mini", "run"],
            instructions="""Initial tasks

  - Run "pwd" to see the directory you are working in. You will only be able to edit files in this directory.
  - Read @CLAUDE.md in the repository root, the git logs and @./ralph/progress_tasks.txt to get up to speed on what was recently worked on.
  - Read the @.ralph/tasks_list.json list file and choose the single highest-priority feature that is not yet done to work on.
  - Do not work on multiple features at once.

  Then, work on that feature only.

  Once complete, you may update that single feature object "passes" property to true.
  
  Update "./.ralph/progress_tasks.txt" with a 3-4 lines summary of what has been done. Be extremely concise. Sacrifice grammar for the sake of concision.
  
  IT IS IMPERATIVE THAT YOU DO NOT UPDATE "./.ralph/tasks_list.json" in any other way - only the single feature "passes" property. It is unacceptable to remove or edit other fields because this could lead to missing or buggy functionality.
  
  If you learn anything useful that might be helpful for future turns - such as implementation or details about writing or updating test cases, please update @CLAUDE.md with this information.

  Then commit these changes, other than the files in the .ralph directory. And report on how you did.""",
        ),
    )

    def get_agent_config(self, agent: Literal["claude", "cursor-agent", "opencode"]) -> AgentConfig:
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
        """Load configuration from JSON file."""
        load_path = path or cls.model_fields["config_file"].default
        if not load_path.exists():
            return cls()

        with load_path.open() as f:
            config_dict = json.load(f)

        # Convert string paths back to Path objects
        for key in ["tasks_file", "progress_file", "config_file"]:
            if key in config_dict:
                config_dict[key] = Path(config_dict[key])

        return cls(**config_dict)


def get_config(config_path: Path | None = None) -> RalphConfig:
    """Get configuration, loading from file if it exists, otherwise using defaults."""
    if config_path:
        return RalphConfig.load(config_path)
    default_config_path = Path(".ralph/ralph_config.json")
    if default_config_path.exists():
        return RalphConfig.load()
    return RalphConfig()
