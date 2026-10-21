---
name: autoshift-job
description: Write or change a steps file (graph) with the owner, one step at a time, before /autoshift runs it.
user-invocable: false
---
Start from `examples/hello/hello.json` or `examples/team/team.json`. Per step ask the owner: what it does (agent,
gate, code, ask), its goal, which folders an agent may write (`--rw`), and what runs after it on PASS or FAIL.
Every agent step needs a gate after it whose check script lives outside the repo (`trusted_gate`). Validate with
`bin/autoshift-config show FILE`. Nothing runs until the owner starts it with `/autoshift FILE`.
