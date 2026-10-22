#!/usr/bin/env python3
"""Adapter that runs one Antigravity (agy) task in print mode.
Usage: agy.py --handoff FILE --output FILE --model MODEL
The caller MUST run this inside adapters/sandbox.sh (the permission bypass below is safe only there).
"""
import argparse
import json
import subprocess
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--handoff',required=True)
    p.add_argument('--output',required=True);p.add_argument('--model',required=True)
    a=p.parse_args()
    instruction='Read the attached handoff; execute precisely the bounded task. '+Path(a.handoff).read_text()
    cmd=['agy','--model',a.model,'--output-format','stream-json',
         '--dangerously-skip-permissions','--disable-slash-commands','-p',instruction]
    # Permission bypass flag is safe ONLY because the caller always wraps this in a restrictive sandbox.
    result=subprocess.run(cmd,capture_output=True,text=True,check=False)
    Path(a.output).write_text(result.stdout)
    print(json.dumps({'claims':[],'agy_stream_path':a.output}))
    raise SystemExit(result.returncode)
if __name__=='__main__':main()
