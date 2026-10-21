"""Admission rails: sample per-provider adapter reports; fail closed. K8 [§7 S30,S31]."""
import json
import subprocess
import time
import os


def reading(cfg, provider):
    spec = cfg.get(provider)
    if not spec:
        return {'provider':provider,'admitted':provider=='code',
                'note':'trusted deterministic code' if provider=='code' else 'no quota adapter configured; fail closed'}
    if spec.get('unmetered') is True:
        # An explicit choice to run a tool that has no usage reader (the /autoshift skill asks for it).
        return {'provider':provider,'admitted':True,'state':'UNMETERED','note':'owner chose no usage stop'}
    # '@package/...' in a reader command means a file inside this package.
    package=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cmd = [package+x[len('@package'):] if isinstance(x,str) and x.startswith('@package/') else x for x in spec['cmd']] if spec.get('cmd') else None
    try:
        if cmd:
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=spec.get('timeout',10),check=False)
            if p.returncode != 0: raise ValueError('quota command failed')
            d=json.loads(p.stdout)
        else:
            if os.environ.get('AUTOSHIFT_TEST_STATIC_QUOTA') != '1':
                return {'provider':provider,'admitted':False,'reason':'static-quota-disabled','state':'READER_ERROR'}
            d={'usage_pct':spec['usage_pct'],'at':time.time()}
        if time.time()-d.get('at',0) > spec.get('max_age',300): raise ValueError('stale quota')
        # Separate stops: each declared limit is checked against its own reading.
        split=[(k[:-len('_limit_pct')],spec[k]) for k in ('weekly_limit_pct','five_hour_limit_pct') if k in spec]
        if split:
            over=[]
            for name,limit in split:
                v=d.get(name+'_pct')
                if not isinstance(v,(int,float)) or not 0 <= v <= 100: raise ValueError('missing '+name+' reading')
                if v >= limit: over.append(name)
            return {'provider':provider,'weekly_pct':d.get('weekly_pct'),'five_hour_pct':d.get('five_hour_pct'),
                    'limits':dict(split),'admitted':not over,'state':'OK' if not over else 'OVER_QUOTA:'+','.join(over)}
        if not isinstance(d.get('usage_pct'), (int,float)) or not 0 <= d['usage_pct'] <= 100:
            raise ValueError('missing quota reading')
        return {'provider':provider,'usage_pct':d['usage_pct'],'limit_pct':spec.get('limit_pct',80),
                'admitted':d['usage_pct'] < spec.get('limit_pct',80),'state':'OK' if d['usage_pct'] < spec.get('limit_pct',80) else 'OVER_QUOTA'}
    except (OSError,ValueError,subprocess.TimeoutExpired,KeyError) as e:
        return {'provider':provider,'admitted':False,'reason':type(e).__name__,'state':'READER_ERROR'}
