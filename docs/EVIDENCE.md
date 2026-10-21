# What a result is

Every step result in the journal is `{node, attempt, rc, status, artifacts: [{path, sha256, size}], missing, claims,
signature, handoff, stdout_sha256, stderr_sha256, usage}`. The kernel decides PASS or FAIL only from the exit code
and the declared artifacts (hashed fresh after the step); what an agent says about its work is stored as a claim
and never read for a decision. A check's artifact that already existed unchanged before it ran does not count.

Each agent attempt gets a new handoff file with the goal, the base commit, the previous attempt's result and the
next action; this file is the only memory one attempt passes to the next. Raw output is kept under `STATE/raw/`.
