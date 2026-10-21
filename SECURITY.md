# Security

AutoShift runs coding agents unattended, so its design assumes an agent may try to fake its own success.

- Agents run inside bubblewrap with an empty home, a private `/tmp`, a cleared environment and only their declared
  `--rw` folders writable. Network is off unless a step turns it on.
- Checks run from a folder outside the repository that agents cannot write, with the code under test read-only.
  PASS comes only from the check's exit code and fresh artifacts, never from what an agent says.
- The journal lives outside the repository and outside every writable folder. Each run works in its own git copy;
  your branch changes only when every check passed and you set `merge_on_pass`.
- Worker sign-ins are separate homes under `~/.local/state/autoshift/`, never your own logins.

Limits: bubblewrap is not a virtual machine; a kernel or bubblewrap bug can break isolation. Agents with network
access can reach the internet. Review what a run merged.

Report a vulnerability privately through GitHub's security advisories for this repository.
