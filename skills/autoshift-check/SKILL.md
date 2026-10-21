---
name: autoshift-check
description: Check a running AutoShift run: the status tree plus one verdict line, from the journal and the real agent transcripts.
user-invocable: false
---
1. `bin/autoshift --graph STATE/graph.json --repo REPO --state STATE status`: show the status tree as a code block.
2. For each step shown RUNNING, read the end of its real transcript `STATE/raw/<step>-<attempt>.stdout` and `.stderr`
   (never judge from status text alone).
3. One verdict line: on track, stuck (no new transcript bytes since the last check), or failing (with the step).
