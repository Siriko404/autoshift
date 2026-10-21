---
name: autoshift-setup
description: Ask the owner every run setting of a steps file and write the run file (step 3-4 of /autoshift).
user-invocable: false
---
`CFG` = `$(autoshift --home)/bin/autoshift-config`. `CFG show GRAPH`, then ask the owner every setting it lists with
AskUserQuestion exactly as `/autoshift` step 3 says (never skip one, never choose for the owner).
Then `CFG apply GRAPH STATE/graph.json key=value ...`; on `refusing:` ask that one again.
