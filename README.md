# Ralph Loop

CLI utility for running AI agent loops (Opencode, Claude, and Cursor) to work through task queues defined in `tasks_list.json`.

The `ralph-loop` CLI utility provides a unified interface for running agent loops with configuration management.

## Installation

#### Standard User Installation (recommended)

This installs to `~/.local/bin` (standard user installation directory):

```bash
uv pip install --prefix ~/.local -e .
```

Or install with development dependencies:

```bash
uv pip install --prefix ~/.local -e ".[dev]"
```

**Note:** Make sure `~/.local/bin` is in your `PATH`. Add this to your `~/.zshrc` or `~/.bashrc` if needed:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

#### Installation to `~/.bin`

To install specifically to `~/.bin`:

**Option 1: Symlink from standard location (recommended)**
```bash
# Install to standard location
uv pip install --prefix ~/.local -e .

# Create symlink to ~/.bin
mkdir -p ~/.bin
ln -s ~/.local/bin/ralph-loop ~/.bin/ralph-loop
```

**Option 2: Direct installation to ~/.bin**
```bash
# Create ~/.bin if it doesn't exist
mkdir -p ~/.bin

# Install using --prefix (creates bin/, lib/, etc. under ~)
uv pip install --prefix ~ -e .
```

This installs to `~/bin/ralph-loop`. If you specifically need `~/.bin` (with a dot), use Option 1 (symlink).

**Note:** Make sure `~/.bin` (or `~/bin`) is in your `PATH`. Add this to your `~/.zshrc` or `~/.bashrc`:

```bash
export PATH="$HOME/.bin:$PATH"  # or "$HOME/bin:$PATH" if using ~/bin
```

#### Verify Installation

After installation, verify the command is available:

```bash
which ralph-loop
ralph-loop --help
```

### Usage

Run an agent loop:

```bash
ralph-loop run <agent> [--iterations N] [--config PATH]
```

Where `<agent>` is one of:
- `claude` - Run Claude agent
- `cursor-agent` - Run Cursor agent (with real-time progress streaming)
- `opencode` - Run Opencode agent

**Note:** The `cursor-agent` option provides real-time progress tracking, showing:
- Model being used
- Character generation progress
- Tool calls (file reads/writes) with line counts
- Completion statistics

Options:
- `--iterations`, `-n`: Number of iterations to run (defaults to number of incomplete tasks)
- `--config`: Path to configuration file (defaults to `.ralph/ralph_config.json`)

Examples:

```bash
# Run Claude agent with default iterations (count of incomplete tasks)
ralph-loop run claude

# Run Cursor agent for 5 iterations
ralph-loop run cursor-agent --iterations 5

# Run Opencode agent with custom config
ralph-loop run opencode --config /path/to/config.json

# Run Cursor agent with real-time progress (shows streaming updates)
ralph-loop run cursor-agent
```

### Configuration

Create or recreate the configuration file:

```bash
ralph-loop config --recreate
```

This creates `.ralph/ralph_config.json` with default agent commands and instructions. You can edit this file to customize:

- Agent command paths and arguments
- Instructions passed to each agent
- File paths for tasks and progress files

View current configuration:

```bash
ralph-loop config
```

## Task Guidelines

- Always update only the `passes` field of the task you finish; do not edit other fields in `tasks_list.json`.
- Log a concise 3–4 line summary of your work in `progress_tasks.txt`.
- Pick the highest-priority outstanding task and focus on it until completion.

## Development

Run tests:

```bash
pytest
```

With coverage:

```bash
pytest --cov=ralph_loop --cov-report=term-missing
```
