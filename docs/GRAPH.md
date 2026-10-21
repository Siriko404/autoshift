# Steps file reference

A steps file (graph) is JSON: `{"name", "nodes": [...], "edges": [...], "wip", "quota", "merge_on_pass"}`.
The kernel validates it before running and refuses anything it cannot check.

## Top level
| key | meaning |
|---|---|
| `nodes` | the steps (required, at least one) |
| `edges` | arrows `{"from": ID, "to": ID, "on": ["PASS"]}`; `on` is any of `PASS`, `FAIL`, `BLOCKED`, `SKIP` (default `PASS`). A step runs when every incoming arrow's condition holds. Cycles are refused: unroll a loop into numbered steps. |
| `wip` | how many steps may run at once (1-128, default 2) |
| `quota` | per tool: `{"cmd": [...], "weekly_limit_pct": 80, "five_hour_limit_pct": 90}` (a reader command printing `{"weekly_pct", "five_hour_pct", "at"}`), or `{"unmetered": true}`. A tool with no entry is refused (fail closed). `@package/` in `cmd` means this package's folder. |
| `merge_on_pass` | `true`: when every step passed, fast-forward your branch to the run's branch. Default `false`: the work stays on branch `autoshift/<state name>`. |
| `audit_policy` | optional rules that insert reviewer agents after the check of workers whose `paths` match. |

## Steps (`nodes`)
Every step has `id` (letters, digits, `_.-`) and `kind`. Optional: `lane` (steps in different lanes run in parallel;
one at a time per lane), `timeout` (seconds, default 300), `max_attempts` (default 1).

| kind | fields | what it does |
|---|---|---|
| `agent` | `goal`, `tiers: [{"provider": "claude"|"codex"|"opencode"|"agy", "model": "..."}]`, `sandbox: ["@package/adapters/sandbox.sh", "--provider", P, "--rw", FOLDER, "--net", "1"]`, `paths` | starts a fresh agent session with a handoff file; on a repeated identical failure it moves to the next tier. It can write only its `--rw` folders. |
| `gate` | `trusted_gate: {"root": "@package" or an absolute folder outside the repo, "entry": "script.sh", "code_paths": [...]}`, `artifacts: [".autoshift-gate-output/NAME"]`, `cmd` (ignored when `trusted_gate` is set) | runs your check script with the code read-only; `trusted_gate.env` lists extra environment variables it may see. PASS only if it exits 0 and writes every declared artifact fresh. Required for every check in a graph that has agents. |
| `code` | `cmd: [argv]`, `artifacts` | runs a command. |
| `ask` | `goal` | waits for `answer ID TEXT --outcome PASS|FAIL`. |
| `fanout` | `items`, `template` | expands into one step per item (`${item}` in `goal`, `lane`, `paths`, `artifacts`). |
| `join` | | a plain meeting point for arrows. |
| `wake` | `on: ["start"]` or signal names | starts when the run starts or when `signal NAME` is sent. |

Examples: `examples/hello/hello.json`, `examples/team/team.json`, `examples/g3-pipeline.json` (commands only),
`examples/g2-ralph.json` (an agent retried through an unrolled loop).
