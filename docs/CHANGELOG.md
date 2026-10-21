# Changelog

## 0.1.0 (2026-10-21)
First public release.
- Kernel: steps file in, run. Step kinds agent, gate, code, ask, fanout, join, wake; lanes run in parallel;
  hash-chained journal with replay and kill recovery; checks run from a folder agents cannot write.
- Agents for Claude Code, Codex, OpenCode and Antigravity, each inside a bubblewrap sandbox with its own worker login.
- Each run works in its own git copy; your branch changes only when every step passed and `merge_on_pass` is true.
- Separate weekly and 5-hour usage stops; `bin/autoshift-config` and the `/autoshift` skill ask every setting first.
- Examples: one agent with a check, two agents in parallel, a commands-only pipeline, an optional planner flow.
