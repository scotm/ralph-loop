"""Loop execution logic for running agents."""

import json
import signal
import subprocess
import sys
import time
from typing import Literal

from ralph_loop.config import AgentConfig, RalphConfig
from ralph_loop.tasks import TasksFile


class LoopRunner:
    """Manages execution of agent loops."""

    def __init__(self, config: RalphConfig):
        """Initialize with configuration."""
        self.config = config
        self.tasks_file = TasksFile(config.tasks_file)
        self.completed = 0
        self._interrupted = False

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful interruption."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame) -> None:  # type: ignore
        """Handle interrupt signals."""
        self._interrupted = True
        print(f"\nInterrupted after {self.completed} iteration(s)")
        sys.exit(130)

    def _parse_stream_json(self, line: str) -> dict | None:
        """Parse a JSON line from stream output."""
        try:
            return json.loads(line.strip())
        except (json.JSONDecodeError, ValueError):
            return None

    def _handle_streaming_output(
        self, process: subprocess.Popen[str], agent: Literal["claude", "cursor-agent", "opencode"], command: list[str]
    ) -> int:
        """Handle streaming output for cursor-agent with real-time progress."""
        accumulated_text = ""
        tool_count = 0
        start_time = time.time()

        if process.stdout is None:
            raise RuntimeError("Process stdout is not available")

        try:
            for line in process.stdout:
                if self._interrupted:
                    process.terminate()
                    break

                data = self._parse_stream_json(line)
                if not data:
                    # Skip non-JSON lines (might be error messages or other output)
                    continue

                event_type = data.get("type", "")
                subtype = data.get("subtype", "")

                if event_type == "system" and subtype == "init":
                    model = data.get("model", "unknown")
                    print(f"🤖 Using model: {model}")

                elif event_type == "assistant":
                    # Accumulate incremental text deltas for smooth progress
                    message = data.get("message", {})
                    content = message.get("content", [])
                    if content and isinstance(content[0], dict):
                        text = content[0].get("text", "")
                        if text:
                            accumulated_text += text
                            # Show live progress (updates with each character delta)
                            print(f"\r📝 Generating: {len(accumulated_text)} chars", end="", flush=True)

                elif event_type == "tool_call":
                    if subtype == "started":
                        tool_count += 1
                        tool_call = data.get("tool_call", {})

                        # Check for writeToolCall
                        if "writeToolCall" in tool_call:
                            path = tool_call["writeToolCall"].get("args", {}).get("path", "unknown")
                            print(f"\n🔧 Tool #{tool_count}: Creating {path}")

                        # Check for readToolCall
                        elif "readToolCall" in tool_call:
                            path = tool_call["readToolCall"].get("args", {}).get("path", "unknown")
                            print(f"\n📖 Tool #{tool_count}: Reading {path}")

                    elif subtype == "completed":
                        tool_call = data.get("tool_call", {})

                        # Check for writeToolCall result
                        if "writeToolCall" in tool_call:
                            result = tool_call["writeToolCall"].get("result", {})
                            if "success" in result:
                                success = result["success"]
                                lines = success.get("linesCreated", 0)
                                size = success.get("fileSize", 0)
                                print(f" ✅ Created {lines} lines ({size} bytes)")

                        # Check for readToolCall result
                        elif "readToolCall" in tool_call:
                            result = tool_call["readToolCall"].get("result", {})
                            if "success" in result:
                                success = result["success"]
                                lines = success.get("totalLines", 0)
                                print(f" ✅ Read {lines} lines")

                elif event_type == "result":
                    duration_ms = data.get("duration_ms", 0)
                    end_time = time.time()
                    total_time = int(end_time - start_time)
                    print(f"\n\n🎯 Completed in {duration_ms}ms ({total_time}s total)")
                    print(f"📊 Final stats: {tool_count} tools, {len(accumulated_text)} chars generated")
        except KeyboardInterrupt:
            process.terminate()
            process.wait()
            raise
        finally:
            if process.poll() is None:  # Process still running
                process.wait()

        if process.returncode != 0 and not self._interrupted:
            raise subprocess.CalledProcessError(process.returncode, command)

        return process.returncode or 0

    def _run_agent(
        self, agent_config: AgentConfig, instructions: str, agent: Literal["claude", "cursor-agent", "opencode"]
    ) -> int:
        """Run a single agent iteration."""
        command = agent_config.command + [instructions]

        # Check if this is cursor-agent with streaming enabled
        is_streaming = agent == "cursor-agent" and "--output-format" in agent_config.command

        try:
            if is_streaming:
                # Use streaming mode for cursor-agent
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,  # Merge stderr into stdout for streaming
                    text=True,
                    bufsize=1,  # Line buffered
                )
                return self._handle_streaming_output(process, agent, command)
            else:
                # Standard mode for other agents
                result = subprocess.run(
                    command,
                    check=True,
                    text=True,
                )
                return result.returncode
        except FileNotFoundError as e:
            raise RuntimeError(
                f"Agent command not found: {agent_config.command[0]}. "
                "Please ensure the agent is installed and available in PATH."
            ) from e
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Agent command failed with exit code {e.returncode}") from e

    def run(
        self,
        agent: Literal["claude", "cursor-agent", "opencode"],
        iterations: int | None = None,
    ) -> None:
        """Run the agent loop for specified iterations."""
        # Validate tasks file exists
        if not self.tasks_file.exists():
            raise FileNotFoundError(
                f"Tasks file not found: {self.config.tasks_file}. "
                "Please ensure tasks_list.json exists."
            )

        # Count incomplete tasks
        incomplete_count = self.tasks_file.count_incomplete()

        if incomplete_count == 0:
            print(
                "No incomplete tasks found in tasks_list.json (all items have passes: true)\n"
                "Nothing to do. Exiting."
            )
            return

        # Determine iterations
        if iterations is None:
            iterations = incomplete_count
        elif iterations <= 0:
            raise ValueError("Iterations must be a positive integer")

        print(f"Found {incomplete_count} incomplete task(s) to work on")

        # Get agent configuration
        agent_config = self.config.get_agent_config(agent)

        # Set up signal handlers
        self._setup_signal_handlers()

        # Run loop
        try:
            for i in range(1, iterations + 1):
                if self._interrupted:
                    break

                print(f"Iteration {i} of {iterations}")
                self._run_agent(agent_config, agent_config.instructions, agent)
                self.completed += 1
                if agent != "cursor-agent" or "--output-format" not in agent_config.command:
                    print(f"Completed iteration {i}")
                print("----------------------------------------")
        finally:
            # Restore default signal handlers
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)

        if not self._interrupted:
            print(f"All {iterations} iteration(s) completed")
