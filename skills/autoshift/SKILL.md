---
name: autoshift
description: Run one of the owner's steps files (graph) on the AutoShift kernel. `/autoshift [GRAPH]` asks the owner every run setting first, then runs it; `/autoshift status`, `/autoshift stop`, `/autoshift answer NODE TEXT`.
argument-hint: "[GRAPH | status | stop | answer NODE TEXT]"
disable-model-invocation: true
---

# /autoshift

`K` = the folder `autoshift --home` prints (where AutoShift is installed). `AS` = `K/bin/autoshift`,
`CFG` = `K/bin/autoshift-config`.
REPO = the owner's current git repository. STATE = `~/.local/state/autoshift-kernel/<repo dir name>-<graph file name>`.
The run file is `STATE/graph.json`. Owner-facing text: short, plain, no tables except the settings summary.

## `/autoshift [GRAPH]`: ask every setting, then run
1. **Steps file.** GRAPH from the argument. If none, ask which one with AskUserQuestion; options are the files
   under `K/examples/` (`hello/hello.json`, `team/team.json`) plus any `*.json` the owner names.
2. **Read the settings.** `CFG show GRAPH`. It prints every setting with its current value.
3. **Ask every setting.** Use AskUserQuestion, at most 4 questions per call, as many calls as
   needed. The current value is the first option, labelled "Keep (Recommended)", with the value in its description.
   Never skip a setting and never choose one for the owner.
   - `weekly_stop`: stop starting new agents at this weekly Claude usage percent (suggested 80).
   - `five_hour_stop`: same for the 5-hour Claude usage (suggested 90).
   - `agents_at_once`: how many agents may run at the same time.
   - `merge_on_pass`: every run works in its own copy on branch `autoshift/<run>`. When every check passes, merge it
     into the owner's branch (`true`) or leave it on that branch for the owner to review (`false`, recommended).
     A failed or unfinished run never changes the owner's files.
   - For each agent step `<id>`: `<id>.tool` and `<id>.model` together in one question (options such as Claude
     Haiku, Claude Sonnet, Codex, OpenCode, Antigravity, each with the models the owner uses), and
     `<id>.timeout` with `<id>.attempts` in one question.
   - For each tool other than Claude that a step uses: `<tool>.unmetered`: "This tool has no usage reader. Run it
     without a usage stop?" (Yes = `true`, No = `false`; with `false` the kernel refuses to start that step).
4. **Apply.** `CFG apply GRAPH STATE/graph.json key=value ...` with every answer. On `refusing:` ask that one
   question again.
5. **Show** the settings in force as one compact table, then start:
   - `AS --graph STATE/graph.json --repo REPO --state STATE init`
   - `AS --graph STATE/graph.json --repo REPO --state STATE run` with `run_in_background`.
   Tell the owner it is running and that `/autoshift status` shows progress.
6. **When it ends,** show `AS ... status`, the run's last output line (merged, or which branch holds the work),
   and one line: passed, failed, cost (the `usage` lines). REPO must be the top folder of a git repository with no
   uncommitted changes; otherwise the run refuses to start: say so.
   Exit code 3 means a step failed or waits for an answer: say which.

## `/autoshift status`
`AS --graph STATE/graph.json --repo REPO --state STATE status`; show it as a code block. Nothing else.

## `/autoshift stop`
`AS ... stop`. New steps stop starting; running agents finish. Say so in one line. `AS ... resume` continues.

## `/autoshift answer NODE TEXT`
`AS ... answer NODE TEXT --outcome PASS|FAIL` for an `ask` step. Only the owner's own words count as the answer.

## Sign-in (once per tool)
A tool's first run needs its own worker sign-in, never the owner's own login. If a step fails with
"worker login missing", give the owner the one line: `! $(autoshift --home)/adapters/sandbox.sh --login TOOL`
(TOOL = claude, codex, opencode or agy).
