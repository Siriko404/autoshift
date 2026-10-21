# AutoShift

A small kernel for running teams of coding agents from a steps file you write. Nothing is built in: no planner,
no fixed flow. Agents can be Claude Code, Codex, OpenCode or Antigravity; each runs locked in a sandbox, and a
check it cannot touch decides whether its work passed.

**A steps file** (`*.json`) lists steps and the arrows between them. A step is one of:
- `agent`: runs a tool with the model and goal you write, in a sandbox that can write only the folders you list.
- `gate`: your check script, run from a folder no agent can write. Its exit code decides PASS or FAIL.
- `code`: any command. `ask`: waits for your answer. `fanout` / `join`: run steps side by side, then wait.

Arrows say which step runs after which, and on which result. Steps in different `lane`s run at the same time.
Every step is written to a journal; if the program is killed, `run` continues where it stopped.

**Your files are safe:** each run works in its own git copy on branch `autoshift/<run>`. Your branch changes only
when every check passed and `merge_on_pass` is true; a failed run leaves your files untouched.

## Install
Needs Linux, Python 3.12+, git and bubblewrap (`bwrap`). No Python packages.
```sh
git clone https://github.com/Siriko404/autoshift && cd autoshift && ./install.sh
adapters/sandbox.sh --login claude     # once per tool: claude, codex, opencode, agy (a separate worker login)
```

## Use
```sh
examples/hello/run.sh                          # one agent writes a file, a check verifies it, on a scratch repo
examples/hello/run.sh examples/team/team.json  # two agents in parallel, then one check
AUTOSHIFT_UNMETERED=1 examples/hello/run.sh    # same, with no Claude usage stop (see docs/ADAPTERS.md)
autoshift --graph FILE --repo REPO --state STATE init|run|status|stop|resume|answer
autoshift-config show|apply FILE               # list or set every run setting
```
In Claude Code, `/autoshift FILE` asks you every setting first (usage stops, agents at once, merge or not, tool and
model per step), then runs it.

Docs: [steps file](docs/GRAPH.md) · [tools](docs/ADAPTERS.md) · [operating a run](docs/OPERATIONS.md) ·
[results](docs/EVIDENCE.md) · [security](SECURITY.md). Tests: `tests/run_all.sh`. License: MIT.
