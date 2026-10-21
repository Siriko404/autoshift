# Optional example: a planner flow

`production.py` is a ready-made flow built on the kernel, not part of it: a planner agent writes a task list, each
task gets its own git worktree, a worker, a locked check, optional reviewers, and a merge (risky task classes wait
for an approval file). Run it with `python3 examples/g1-planner/run.py --graph G --repo R --state S run [--follow]`.
Its settings format is in `test_production.py`. Tested with stand-in agents only.
