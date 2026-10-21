# Operating a run

```sh
A="bin/autoshift --graph FILE --repo REPO --state STATE"
$A init        # create the journal
$A run         # run until every step is done, failed or waiting; exit 0 = all passed, 3 = not
$A status      # the step tree, usage and open questions
$A stop        # no new steps start; running ones finish. $A resume continues
$A answer ID TEXT --outcome PASS|FAIL      # reply to an ask step
$A replay      # rebuild the state from the journal and compare (REPLAY_OK)
$A reconcile ID --rerun|--accept           # settle a step that was running when the driver died
```

- `REPO` must be the top folder of a git repository with no uncommitted changes. The run works in its own copy
  (`STATE-work`, branch `autoshift/<state name>`); your branch changes only when every step passed and
  `merge_on_pass` is true, and only by fast-forward.
- `STATE` must be outside `REPO`. It holds the journal (`events.jsonl`, hash-chained), the handoffs, the raw agent
  transcripts (`raw/`, mode 0600) and the check outputs.
- Killed mid-run: start `run` again. A step that was running is marked uncertain; check its work, then
  `reconcile ID --rerun` or `--accept`. Nothing is repeated silently.
- One driver per state folder (a lock refuses a second one). Nothing runs in the background on its own.
- `AUTOSHIFT_TEST_SANDBOX` and `AUTOSHIFT_TEST_STATIC_QUOTA` exist only for the test suite. Never set them for real runs.
