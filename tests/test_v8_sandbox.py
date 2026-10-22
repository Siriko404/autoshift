"""Stub bwrap argv inspection with CLI shims at the actual ~/.local/bin placement."""
import os,subprocess,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.providers import command
base=Path(__file__).resolve().parents[1]
for p in ('claude','codex','opencode','agy'):
    argv=command(p,'test-model','/a/handoff','/a/output')
    assert argv and (argv[0]==p or p=='agy' and argv[0]=='python3')
    if p=='agy':assert str(base/'adapters/agy.py') in argv
    if p=='claude':assert argv[argv.index('--permission-mode')+1]=='bypassPermissions'
    # codex-cli 0.159 rejects --full-auto; the launch line must use flags the installed CLI accepts.
    if p=='codex':assert '--full-auto' not in argv and argv[argv.index('--sandbox')+1]=='workspace-write'
with tempfile.TemporaryDirectory() as d:
    h=Path(d);bindir=h/'.local/bin';bindir.mkdir(parents=True)
    (h/'.local/share/mise').mkdir(parents=True)
    for cli in ('claude','codex','opencode','agy'):
        x=bindir/cli;x.write_text('#!/bin/sh\necho CLI_STUB\n');x.chmod(0o755)
    m=bindir/'mise';m.write_text('#!/bin/sh\nexit 1\n');m.chmod(0o755)   # hermetic: no real mise lookup
    b=bindir/'bwrap';b.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n');b.chmod(0o755)
    for provider in ('codex','opencode','agy'):(h/'.local/state/autoshift'/(provider+'-worker')).mkdir(parents=True)
    (h/'.local/state/autoshift/codex-worker/auth.json').write_text('{}')
    (h/'.local/state/autoshift/opencode-worker/data/opencode').mkdir(parents=True);(h/'.local/state/autoshift/opencode-worker/data/opencode/auth.json').write_text('{}')
    (h/'.local/state/autoshift/agy-worker/antigravity-cli').mkdir()
    ch=h/'.local/state/autoshift/claude-worker';ch.mkdir(parents=True);(ch/'.credentials.json').write_text('{}')
    env={**os.environ,'HOME':str(h),'PATH':str(bindir)+':/usr/bin:/bin'}
    for provider in ('claude','codex','opencode','agy'):
        run=subprocess.run(['bash',str(base/'adapters/sandbox.sh'),'--provider',provider,'--net','0','--ro',str(h), '--',provider,'--version'],env=env,capture_output=True,text=True)
        assert run.returncode==0,(provider,run.stderr)
        result=run.stdout.splitlines()
        # Production run found ~/.local/bin full of mise shims: bind only the real executable, never the whole directory.
        assert str(bindir/provider) in result and str(bindir) not in result and '--ro-bind' in result and '/usr' in result
        if provider=='claude':assert 'CLAUDE_CONFIG_DIR' in result
        if provider=='codex':assert 'CODEX_HOME' in result
        if provider=='opencode':assert 'XDG_CONFIG_HOME' in result and 'OPENCODE_PERMISSION' in result and '{"external_directory":"allow"}' in result
        if provider=='agy':assert 'AGY_HOME' in result
print('V8_SANDBOX_ARGV_OK fake_~local_bin_all_four_providers')
