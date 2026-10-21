"""Proof is rc and exact artifact bytes. Claims never control transitions. K4 K9 [§9 S25,S65]."""
import hashlib
from pathlib import Path


def collect(base, artifacts):
    base = Path(base).resolve()
    found=[];missing=[]
    for rel in artifacts:
        p=base/rel
        try:
            rp=p.resolve(strict=True)
            if not rp.is_relative_to(base) or not rp.is_file(): raise ValueError('unsafe artifact')
            h=hashlib.sha256(rp.read_bytes()).hexdigest()
            found.append({'path':rel,'sha256':h,'size':rp.stat().st_size})
        except (OSError,ValueError):missing.append(rel)
    return found,missing


def verdict(rc, missing, timed_out=False, uncertain=False):
    if uncertain:return 'BLOCKED'
    if timed_out:return 'FAIL'
    if rc is None:return 'BLOCKED'
    if rc != 0 or missing:return 'FAIL'
    return 'PASS'
