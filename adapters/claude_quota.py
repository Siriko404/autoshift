#!/usr/bin/env python3
"""Claude usage reader for the kernel's usage stops. Prints {"usage_pct", "at", "weekly_pct", "five_hour_pct"}.

The kernel does not ship a way to read your Claude plan usage. Supply one of:
  1. AUTOSHIFT_CLAUDE_USAGE_CMD = a command that prints {"weekly_pct": N, "five_hour_pct": N, "at": UNIX_SECONDS}
  2. a file adapters/legacy_claude_quota.py of your own with read() -> {"ok": true, "seven_day": N, "five_hour": N, "at": T}
With neither, this exits 3 and the kernel refuses to start Claude steps (fail closed). To run anyway, choose it
explicitly: autoshift-config apply FILE OUT claude.unmetered=true.
"""
import json
import os
import shlex
import subprocess
import sys
import time

try:
    cmd = os.environ.get('AUTOSHIFT_CLAUDE_USAGE_CMD')
    if cmd:
        p = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=20)
        if p.returncode != 0:
            raise ValueError('usage command failed')
        d = json.loads(p.stdout)
        week, five = float(d['weekly_pct']), float(d['five_hour_pct'])
        at = d.get('at', time.time())
    else:
        import legacy_claude_quota
        d = legacy_claude_quota.read()
        if not d.get('ok'):
            raise ValueError('unavailable')
        week, five, at = float(d['seven_day']), float(d['five_hour']), d.get('at', time.time())
    print(json.dumps({'usage_pct': max(week, five), 'at': at, 'weekly_pct': week, 'five_hour_pct': five}))
except ImportError:
    print('no Claude usage reader installed: see adapters/claude_quota.py and docs/ADAPTERS.md', file=sys.stderr)
    raise SystemExit(3)
except Exception:
    raise SystemExit(3)
