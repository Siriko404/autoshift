#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
python3 - "$HERE/autoshift" <<'PY'
import pathlib,sys
files=list(pathlib.Path(sys.argv[1]).rglob('*.py'))
print('kernel_lines',sum(len(f.read_text().splitlines()) for f in files),'files',len(files))
for f in files:print(f.name,len(f.read_text().splitlines()))
PY
