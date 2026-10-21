---
name: autoshift-ask
description: Handle a step that waits for an answer (an ask step, or a step that failed at every attempt).
user-invocable: false
---
`status` lists open asks. Show the owner the question and the evidence (`STATE/raw/`, the check's output). Only the
owner's own words are an answer: `bin/autoshift ... answer NODE TEXT --outcome PASS|FAIL` for an ask step. A failed
step is rerun only by `reconcile NODE --rerun` after the owner says so.
