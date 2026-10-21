# Tools (providers)

Every agent runs inside `adapters/sandbox.sh` (bubblewrap): an empty home, a private `/tmp`, a cleared environment,
no network unless the step says `--net 1`, and only the step's `--rw` folders writable. The sandbox binds the real
program (found with `mise where` or on `PATH`, never a wrapper script that rewrites its own files).

| provider | command the kernel runs | worker sign-in |
|---|---|---|
| `claude` | `claude --print --permission-mode bypassPermissions --model M --output-format json "Read handoff at H; execute task."` | `adapters/sandbox.sh --login claude` |
| `codex` | `codex exec --model M --sandbox workspace-write --skip-git-repo-check --output-last-message O "Read handoff at H; execute task."` | `adapters/sandbox.sh --login codex` |
| `opencode` | `opencode run --model M "Read task at H"` (M is `provider/model`) | `adapters/sandbox.sh --login opencode` |
| `agy` | `python3 adapters/agy_gjob.py --handoff H --output O --model M` | `adapters/sandbox.sh --login agy` |

Each tool signs in once into its own worker home under `~/.local/state/autoshift/<tool>-worker`, never your own
login. Tested with claude 2.1.293, codex 0.159.2, opencode 1.19.0, agy 1.4.2 (`--version` inside the sandbox);
real tasks were run with Claude only.

**Site additions:** if `~/.config/autoshift/sandbox-extra.sh` exists (or `AUTOSHIFT_SANDBOX_EXTRA` names a file),
the sandbox sources it for Claude workers, so you can add your own read-only binds or a wrapper command (`PRE`).

**Usage stops:** a graph's `quota.claude.cmd` runs a reader that prints `{"weekly_pct", "five_hour_pct", "at"}`;
the kernel starts a Claude step only if both numbers are under their stops (`weekly_limit_pct`,
`five_hour_limit_pct`) and the reading is fresh. `adapters/claude_quota.py` is that reader's front door: it runs
the command in `AUTOSHIFT_CLAUDE_USAGE_CMD` if set, otherwise exits 3 and the kernel refuses to start Claude
steps (fail closed). AutoShift does not ship a way to read your plan usage; bring your own command. To run with no
usage stop, choose it explicitly: `autoshift-config apply FILE OUT claude.unmetered=true`. Tools other than Claude
never have a reader; they need the same explicit `<tool>.unmetered=true`.
