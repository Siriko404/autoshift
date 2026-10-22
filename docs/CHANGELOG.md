# Changelog

## 0.2.0 (2026-10-21)
- `host` steps: a `code` step can run your own pinned script outside the sandbox, for tools that bring their own sandbox.
  The script's folder is hash-pinned and must lie outside the repository; see docs/GRAPH.md.

## 0.1.1 (2026-10-21)
- OpenCode agents can read their task file (the sandbox sets `OPENCODE_PERMISSION`); before, the agent was refused and did nothing.
- `--login agy` hides the desktop session bus, so Antigravity signs in fresh and keeps its token in the worker home.
- The Antigravity adapter is now `adapters/agy.py`.
- Each of the four tools has passed one real task (write a file, then a check).

## 0.1.0 (2026-10-21)
First public release.
- Kernel: steps file in, run. Step kinds agent, gate, code, ask, fanout, join, wake; lanes run in parallel;
  hash-chained journal with replay and kill recovery; checks run from a folder agents cannot write.
- Agents for Claude Code, Codex, OpenCode and Antigravity, each inside a bubblewrap sandbox with its own worker login.
- Each run works in its own git copy; your branch changes only when every step passed and `merge_on_pass` is true.
- Separate weekly and 5-hour usage stops; `bin/autoshift-config` and the `/autoshift` skill ask every setting first.
- Examples: one agent with a check, two agents in parallel, a commands-only pipeline, an optional planner flow.
