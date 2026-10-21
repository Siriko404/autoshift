---
name: autoshift-run
description: Start a run file that /autoshift-setup wrote (step 5 of /autoshift).
user-invocable: false
---
`bin/autoshift` is `$(autoshift --home)/bin/autoshift`: `bin/autoshift --graph STATE/graph.json --repo REPO --state STATE init`, then the same
with `run` as a background command. The run works in its own git copy; REPO must be the top of a clean git repo.
