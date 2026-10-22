# Security

AutoShift runs coding agents unattended, so its design assumes an agent may try to fake its own success.

- Agents run inside bubblewrap with an empty home, a private `/tmp`, a cleared environment and only their declared
  `--rw` folders writable. Network is off unless a step turns it on.
- Checks run from a folder outside the repository that agents cannot write, with the code under test read-only.
  PASS comes only from the check's exit code and fresh artifacts, never from what an agent says.
- The journal lives outside the repository and outside every writable folder. Each run works in its own git copy;
  your branch changes only when every check passed and you set `merge_on_pass`.
- One opt-in exception: a `host` step (docs/GRAPH.md) runs a script you pinned outside the sandbox, with your full permissions. It
  runs only from a folder outside the repository, only while its hash matches the journalled pin, and only if you wrote it into the steps file.
- Worker sign-ins are separate homes under `~/.local/state/autoshift/`, never your own logins.

Limits:
- bubblewrap is not a virtual machine; a kernel or bubblewrap bug can break isolation.
- A step with network on (every step that calls a model) shares this computer's network. It can reach the internet,
  any service listening on the loopback address (127.0.0.1), and unix sockets in the abstract namespace. Tested:
  with `--net 1` a sandboxed process connected to a local listener; with `--net 0` it was refused. Stop unauthenticated
  local services (dev servers, admin pages) while a run has network on, or run AutoShift inside a VM.
- `merge_on_pass` merges whatever the agent wrote, including files that run later (hooks, scripts, CI files, editor
  and agent settings). Read the diff before you merge, and leave `merge_on_pass` off for goals you do not trust.
- A steps file is trusted input. A step's own `sandbox` list must start with the package's `adapters/sandbox.sh`;
  anything else is refused. The `AUTOSHIFT_TEST_*` variables are for the test suite and weaken isolation; never set
  them in a real run.

Report a vulnerability privately through GitHub's security advisories for this repository.
