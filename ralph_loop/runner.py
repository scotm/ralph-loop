"""Loop execution logic for running agents."""

import json
import signal
import subprocess
import sys
import time
from typing import Literal

from ralph_loop.config import AgentConfig, RalphConfig
from ralph_loop.tasks import TasksFile

_TOOL_ARG_KEYS = ("command", "pattern", "path", "query", "url", "description", "prompt")


def _tool_call_entry(tool_call: dict) -> tuple[str, dict]:
    """Return the tool name and a payload with ``args``/``result`` keys."""
    for key, value in tool_call.items():
        if isinstance(value, dict) and key.endswith("ToolCall"):
            return key[: -len("ToolCall")], value

    function = tool_call.get("function")
    if isinstance(function, dict):
        args = function.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {"command": args}
        return str(function.get("name", "tool")), {
            "args": args if isinstance(args, dict) else {},
            "result": function.get("result", {}),
        }

    return "tool", {}


def _tool_call_summary(payload: dict) -> str:
    """Pick the most useful argument for a one-line tool description."""
    args = payload.get("args")
    if not isinstance(args, dict):
        return ""
    for key in _TOOL_ARG_KEYS:
        value = args.get(key)
        if isinstance(value, str) and value:
            return value if len(value) <= 120 else value[:117] + "..."
    return ""


def _tool_call_result(payload: dict) -> str:
    """Reduce a tool result to a short human-readable line."""
    result = payload.get("result")
    if not isinstance(result, dict):
        return "done"

    if "rejected" in result:
        rejected = result["rejected"] if isinstance(result["rejected"], dict) else {}
        return f"rejected ({rejected.get('reason') or 'not permitted'})"

    if "error" in result:
        error = result["error"]
        if isinstance(error, dict):
            error = error.get("message") or error.get("error") or "unknown error"
        return f"failed: {error}"

    success = result.get("success")
    if not isinstance(success, dict):
        return "done"

    if "exitCode" in success:
        lines = len((success.get("stdout") or "").splitlines())
        return f"exit {success['exitCode']}, {lines} output line(s)"
    if "linesAdded" in success or "linesRemoved" in success:
        return f"edited (+{success.get('linesAdded', 0)}/-{success.get('linesRemoved', 0)} lines)"
    if "linesCreated" in success:
        return f"wrote {success['linesCreated']} line(s), {success.get('fileSize', 0)} bytes"
    if "totalLines" in success:
        return f"read {success['totalLines']} line(s)"
    if "workspaceResults" in success:
        matched = sum(
            ((workspace or {}).get("content") or {}).get("totalMatchedLines", 0)
            for workspace in (success.get("workspaceResults") or {}).values()
        )
        return f"{matched} match(es)"
    if "content" in success:
        return f"{len((success.get('content') or '').splitlines())} line(s)"
    return "done"


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
        """Handle every cursor-agent stream event and show it as it arrives."""
        generated_chars = 0
        tool_count = 0
        start_time = time.time()
        line_open = False
        message_streamed = False
        thinking_open = False
        dim = "\033[2m" if sys.stdout.isatty() else ""
        reset = "\033[0m" if dim else ""

        def end_line() -> None:
            nonlocal line_open
            if line_open:
                print()
                line_open = False

        def end_thinking() -> None:
            nonlocal thinking_open
            if thinking_open:
                thinking_open = False
                if reset:
                    sys.stdout.write(reset)
                    sys.stdout.flush()
                end_line()

        if process.stdout is None:
            raise RuntimeError("Process stdout is not available")

        try:
            for line in process.stdout:
                if self._interrupted:
                    process.terminate()
                    break

                data = self._parse_stream_json(line)
                if not data:
                    # Non-JSON output (stderr warnings, CLI errors) is still useful.
                    if line.strip():
                        end_thinking()
                        end_line()
                        print(line.rstrip())
                    continue

                event_type = data.get("type", "")
                subtype = data.get("subtype", "")

                if event_type == "system" and subtype == "init":
                    end_thinking()
                    end_line()
                    print(f"🤖 Using model: {data.get('model', 'unknown')}")

                elif event_type == "thinking":
                    text = data.get("text", "")
                    if subtype == "delta" and text:
                        if not thinking_open:
                            end_line()
                            print("💭 ", end="", flush=True)
                            thinking_open = True
                        sys.stdout.write(f"{dim}{text}{reset}")
                        sys.stdout.flush()
                        line_open = not text.endswith("\n")
                    elif subtype == "completed":
                        end_thinking()

                elif event_type == "assistant":
                    parts = (data.get("message") or {}).get("content") or []
                    text = "".join(
                        part.get("text", "")
                        for part in parts
                        if isinstance(part, dict) and part.get("type", "text") == "text"
                    )
                    if not text:
                        continue

                    end_thinking()
                    # stream-json without --stream-partial-output sends finished
                    # messages; with it, deltas repeat in the final flush.
                    is_delta = bool(data.get("timestamp_ms")) and not data.get("model_call_id")
                    if is_delta or not message_streamed:
                        sys.stdout.write(text)
                        sys.stdout.flush()
                        generated_chars += len(text)
                        line_open = not text.endswith("\n")
                    message_streamed = is_delta

                elif event_type == "tool_call":
                    name, payload = _tool_call_entry(data.get("tool_call") or {})
                    if subtype == "started":
                        tool_count += 1
                        end_thinking()
                        end_line()
                        summary = _tool_call_summary(payload)
                        print(f"🔧 {name}: {summary}" if summary else f"🔧 {name}")
                    elif subtype == "completed":
                        end_line()
                        print(f"   ✅ {_tool_call_result(payload)}")

                elif event_type == "result":
                    end_thinking()
                    end_line()
                    if generated_chars == 0:
                        text = data.get("result") or ""
                        if text:
                            print(text)
                    duration_ms = data.get("duration_ms", 0)
                    total_time = int(time.time() - start_time)
                    print(f"\n🎯 Completed in {duration_ms}ms ({total_time}s total)")
                    print(f"📊 Final stats: {tool_count} tools, {generated_chars} chars generated")
        except KeyboardInterrupt:
            process.terminate()
            process.wait()
            raise
        finally:
            end_thinking()
            end_line()
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
