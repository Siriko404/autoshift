"""bin/autoshift-config: every run setting can be listed and set; bad answers are refused."""
import json,subprocess,sys,tempfile
from pathlib import Path
P=Path(__file__).resolve().parents[1];CFG=[sys.executable,str(P/'bin/autoshift-config')]
def run(*a):return subprocess.run(CFG+list(a),capture_output=True,text=True)
team=str(P/'examples/team/team.json')
shown=json.loads(run('show',team).stdout)
for k in ('weekly_stop','five_hour_stop','agents_at_once','merge_on_pass','worker_a.tool','worker_a.model','worker_b.timeout','worker_b.attempts'):
    assert k in shown,k
assert shown['weekly_stop']==80 and shown['five_hour_stop']==90
with tempfile.TemporaryDirectory() as d:
    out=str(Path(d)/'g.json')
    r=run('apply',team,out,'weekly_stop=70','five_hour_stop=85','agents_at_once=1','worker_a.tool=codex',
          'worker_a.model=gpt-6.1-sol','worker_b.attempts=2','codex.unmetered=true','merge_on_pass=true')
    assert r.returncode==0,r.stdout+r.stderr
    g=json.loads(Path(out).read_text());a=[n for n in g['nodes'] if n['id']=='worker_a'][0]
    assert g['quota']['claude']['weekly_limit_pct']==70 and g['quota']['claude']['five_hour_limit_pct']==85
    assert g['wip']==1 and a['tiers'][0]=={'provider':'codex','model':'gpt-6.1-sol'}
    assert a['sandbox'][a['sandbox'].index('--provider')+1]=='codex','sandbox must follow the chosen tool'
    assert g['quota']['codex']=={'unmetered':True} and g['merge_on_pass'] is True
    assert json.loads(run('show',out).stdout)['codex.unmetered'] is True
    r=run('apply',team,out,'claude.unmetered=true','weekly_stop=70')
    g=json.loads(Path(out).read_text())
    assert r.returncode==0 and g['quota']['claude']=={'unmetered':True},'unmetered replaces the reader and ignores the stops'
    assert json.loads(run('show',out).stdout)['claude.unmetered'] is True
    r=run('apply',out,out+'.back','claude.unmetered=false')
    back=json.loads(Path(out+'.back').read_text())['quota']['claude']
    assert r.returncode==0 and back['cmd'][-1].endswith('claude_quota.py') and 'unmetered' not in back
    for bad in ('worker_a.tool=gemini','weekly_stop=0','weekly_stop=101','nosuch=1','check.model=x','codex.unmetered=maybe','merge_on_pass=yes'):
        r=run('apply',team,out+'.bad',bad)
        assert r.returncode==2 and r.stdout.startswith('refusing'),bad
        assert not Path(out+'.bad').exists(),bad
print('CONFIG_OK')
