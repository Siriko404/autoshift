#!/usr/bin/env python3
"""Adapter for known gjob-style agy CLI invocation. 
Usage: agy_gjob.py --handoff FILE --output FILE --model MODEL
The caller MUST use sandbox.sh / project-specific sandbox, with credential home scoped.
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
