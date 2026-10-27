# Config and Agent Prompt Issues

Status snapshot of `ralph-loop` default configuration and agent instructions.

The issues below were found while reviewing `ralph_loop/config.py` and the prompts passed
to agents. The correctness and prompt-semantics issues were fixed in the same change.
This document records the remaining issues, with evidence and suggested fixes.

A follow-up change resolved the open issues below; see [Resolution](#resolution) at the
end. Line references in the issue text describe the pre-fix code.

Reference environment: macOS, Cursor CLI `2026.10.22-27dcf5f`, `pytest` 9.1.1 / Python 3.15.

## Fixed in this change

| Issue | Fix |
| --- | --- |
| Prompts pointed at `./ralph/progress_tasks.txt` (missing dot) | Paths now come from `tasks_file` / `progress_file` config at run time |
| Prompts required `CLAUDE.md`, which many repos do not have | Reads `AGENTS.md` or `CLAUDE.md` if present |
| Prompt claimed the agent could not edit outside the directory | Reworded to an explicit "work only inside this repository" instruction |
| README and errors referenced root `tasks_list.json` | README and runtime messages use the configured paths |
| Three prompt copies had already drifted | One `DEFAULT_INSTRUCTIONS` constant shared by all agents |
| "Highest-priority task" with no priority field | Prompt now uses the first incomplete task in file order |
| No definition of done, no blocked/failure path | Tests must pass before `passes: true`; blocked tasks stay false and record the blocker |
| `.ralph` loop state was not ignored | `.ralph/tasks_list.json` and `.ralph/progress_tasks.txt` added to `.gitignore` |

## Open issues

### 1. Model IDs are hardcoded and age quickly

**Detail.** Every default command pins a model:

- `ralph_loop/config.py:63` — `claude --model opus`
- `ralph_loop/config.py:70-73` — `agent --model composer-2`
- `ralph_loop/config.py:88` — `opencode --model openai/gpt-5.3-codex`

Cursor's `composer-2` alias already resolves to "Composer 2.5" in the stream init
event. The opencode model is provider-specific (`openai/...`) and may not exist for
users on another provider. Git history shows this exact maintenance burden:

```text
2eabf21 2026-03-24 Update agent model versions ... composer from 1.5 to 2 ... gpt-5.3-codex
480e24f 2026-02-12 Update cursor-agent model from composer-1 to composer-1.5
```

**Impact.** A retired model or unknown provider path makes every iteration fail with
an API error. Users must edit `.ralph/ralph_config.json` or run `--recreate` after
each upstream model change.

**Suggested fix.** Drop `--model` and let each CLI use its configured default, or add
a `model` field per agent with an environment override (`RALPH_CURSOR_AGENT__MODEL`).
Prefer CLI defaults because each tool already knows its current model names.

### 2. Permissions are disabled; the prompt is the only guardrail

**Detail.** Defaults run the agents with restrictions removed:

- Claude: `--dangerously-skip-permissions` (`config.py:63`)
- Cursor: `--sandbox disabled` and `--force` (`config.py:74-76`)

Cursor's own help documents `--force` as "Force allow commands unless explicitly
denied" and `--sandbox` as an explicit enable/disable override. The runner also does
not pass `cwd=` to `subprocess` (`runner.py:159-165`, `runner.py:169-173`), so the agent
inherits whatever directory `ralph-loop` was started from.

The prompt now says "Work only inside this repository" (`config.py:12`), but that is a
request to the model, not an enforced boundary.

**Impact.** An unattended loop can edit files outside the repo and run unrestricted
shell commands. This is intentional for unattended use, but it should be a deliberate
choice, not an accident of defaults.

**Suggested fix.** Keep `--force` (needed for unattended edits) but stop disabling the
Cursor sandbox, or pass an explicit workspace/cwd. For Claude, use a permission profile
instead of `--dangerously-skip-permissions`. Document the security tradeoff in the
README next to the run command.

### 3. Existing generated configs keep the old prompts

**Detail.** `ralph-loop config --recreate` writes the full instruction strings into
`.ralph/ralph_config.json` (`cli.py:93-98`). `get_config()` prefers that file whenever
it exists (`config.py:139-141`). Defaults changed in code do not reach anyone who
already generated a config file.

**Impact.** Users upgrading to the fixed prompts still send the old `@./ralph/...`
path and `CLAUDE.md` instruction until they delete or recreate the file. This is a
silent, upgrade-only bug.

**Suggested fix.** Add a config schema version and migrate on load, or store only
overrides in the file and merge over current defaults. At minimum, document the
required `ralph-loop config --recreate` step for this release.

**Evidence.** The file is gitignored (`.gitignore`), so it cannot be updated by
`git pull`; it only changes through `--recreate`.

### 4. An explicit missing config path is silently ignored

**Detail.** `RalphConfig.load()` returns defaults when the path does not exist:

```python
# ralph_loop/config.py:117-122
@classmethod
def load(cls, path: Path | None = None) -> "RalphConfig":
    load_path = path or cls.model_fields["config_file"].default
    if not load_path.exists():
        return cls()
```

`get_config(config_path)` forwards an explicit path unchanged (`config.py:137-138`).
It also never sets `config_file` to the path that was loaded.

**Evidence.**

```text
$ ralph-loop run claude --config /tmp/typo.json
# runs with built-in defaults, no error
```

**Impact.** A typo in `--config` runs the wrong task file and prompts with no warning.
A later `save()` writes to `.ralph/ralph_config.json`, not the requested path.

**Suggested fix.** Raise `FileNotFoundError` when the caller explicitly supplied a
path; set `config_file` to the resolved path when loading; keep the silent-default
behavior only for the implicit default location.

### 5. Agent validation is duplicated in three modules

**Detail.** The agent set appears in:

- `cli.py:20-25` — `valid_agents = ["claude", "cursor-agent", "opencode"]`
- `runner.py:147-148` and `runner.py:185` — `Literal["claude", "cursor-agent", "opencode"]`
- `config.py:93-100` — `agent_map` keys

**Impact.** Adding an agent requires three edits. A mismatch (for example a CLI entry
without a matching `agent_map` key) passes validation and then raises `KeyError` at
run time. The type alias is duplicated in every runner signature.

**Suggested fix.** Define `AGENT_NAMES` and `AgentName = Literal[...]` once in
`config.py`; import them in `cli.py` and `runner.py`.

### 6. `extra="ignore"` hides configuration typos

**Detail.** `RalphConfig` uses Pydantic's `extra="ignore"` (`config.py:41-45`).

**Evidence.** A misspelled key in `.ralph/ralph_config.json`, such as `"cursorAgent"`
or `"task_file"`, is dropped during load. The run continues with the default value.

**Impact.** Users believe their customization is active when it is not. This is worse
for prompt/path settings, where the failure is invisible until the agent reads the
wrong file.

**Suggested fix.** Validate the JSON keys before constructing the model (for example
`extra="forbid"` on a load-only model), and report unknown keys with the file path.

### 7. Task ordering is file order only

**Detail.** `Task` has `category`, `description`, `steps`, and `passes` (`tasks.py:9-15`).
There is no priority or dependency field. The prompt now says to pick the first
incomplete task in file order (`config.py:14`), matching the actual data model.

**Impact.** A large or blocked task at the top of the file starves everything after it.
Users can reorder the JSON manually, but there is no machine-readable way to express
priority or dependencies.

**Suggested fix.** Add optional `priority: int = 0` and sort by it, or document that
file order is the contract (done in the prompt and README). Dependencies would be a
larger feature and should not be added speculatively.

### 8. Streaming detection is a substring check

**Detail.** The runner decides to use the streaming handler if the literal flag is
present anywhere in the command:

```python
# ralph_loop/runner.py:154
is_streaming = agent == "cursor-agent" and "--output-format" in agent_config.command
```

The same condition is duplicated for log suppression at `runner.py:229`.

**Impact.** `--output-format text` also selects the streaming handler; text lines then
fall through the non-JSON branch and are echoed raw. `--output-format json` works only
because the handler tolerates a single terminal event. Any future streaming agent is
excluded unless its name is exactly `cursor-agent`.

**Suggested fix.** Read the flag value (`stream-json` only) in one helper, or add
`streaming: bool = False` to `AgentConfig` and let config decide.

### 9. Workspace trust behavior needs verification

**Detail.** On Cursor CLI `2026.10.22`, running headless in a fresh temporary directory
exited with:

```text
⚠ Workspace Trust Required
  ...
  Pass --trust, --yolo, or -f if you trust this directory
```

The default command includes `--force`, which Cursor's help describes as an alias for
`--yolo`. Whether `--force` alone satisfies the workspace-trust gate was not verified;
the probe used `--trust`.

**Impact.** If `--force` does not satisfy trust, the first loop run in a fresh clone
fails before any work starts, with a non-zero exit and no useful ralph-loop message.

**Suggested fix.** Verify the combination, then either add `--trust` to the default
Cursor command or document one-time interactive trust for each workspace.

## Resolution

| Issue | Verdict | Action |
| --- | --- | --- |
| 1. Hardcoded model IDs | Valid | Defaults no longer pass `--model`; each CLI uses its own default. Users can still pin a model in `.ralph/ralph_config.json`. |
| 2. Permissions disabled | Valid, intentional | Kept the unattended flags, since removing them makes the loop stall on prompts. README now documents the security tradeoff. An explicit `cwd` was not added because the agent already inherits the directory the user starts the loop in. |
| 3. Existing configs keep old prompts | Valid | Added `config_version`. Loading a file created before this version warns and points at `ralph-loop config --recreate`; README documents the upgrade step. |
| 4. Missing explicit config path ignored | Valid | `RalphConfig.load(explicit_path)` raises `FileNotFoundError`; the implicit default path still falls back to defaults. `config_file` is set to the loaded path. |
| 5. Duplicated agent validation | Valid | `AGENT_NAMES` and `AgentName` are defined once in `config.py` and imported by `cli.py` and `runner.py`. |
| 6. `extra="ignore"` hides typos | Valid | Loading validates top-level and per-agent keys against the models and reports unknown keys with the file path. |
| 7. File-order-only task ordering | Valid, accepted limitation | File order remains the contract, as documented in the prompt and README. No speculative priority or dependency fields. |
| 8. Streaming detection is a substring check | Valid | Streaming is now the `AgentConfig.streaming` flag (true for `cursor-agent`) instead of inspecting `--output-format`; future agents can opt in via config. |
| 9. Workspace trust | Not an issue | Verified with Cursor CLI `2026.10.22-27dcf5f`: `agent -p --force` completed in a fresh temp directory without a trust prompt. `--force` is the `--yolo`/`-f` alias that the trust message accepts. |

Verification after the follow-up change:

```text
$ pytest -q
42 passed
```

## Verification for the fixed issues

```text
$ pytest -q
34 passed
```

Prompt rendering check:

```text
$ python -c 'from ralph_loop.config import RalphConfig; from ralph_loop.runner import LoopRunner; \
print(LoopRunner(RalphConfig())._format_instructions(RalphConfig().claude.instructions))'
...
  - Read `.ralph/progress_tasks.txt` ...
  - Read the `.ralph/tasks_list.json` task list and choose the first task whose `passes` field is false.
...
```
