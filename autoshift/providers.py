"""CLI adapter argv construction. Actual sandboxing enforced by runner. K11 [§11 S27]."""


def command(provider, model, handoff, output, overrides=None):
    if overrides and provider in overrides:
        return list(overrides[provider])+[str(handoff),str(output),str(model)]
    if provider == 'claude':
        return ['claude','--print','--permission-mode','bypassPermissions','--model',model,'--output-format','json',
                'Read handoff at '+str(handoff)+'; execute task.']
    if provider == 'codex':
        # codex-cli 0.159 has no --full-auto; its equivalent is codex's own workspace-write sandbox (inside bwrap).
        return ['codex','exec','--model',model,'--sandbox','workspace-write','--skip-git-repo-check',
                '--output-last-message',str(output),
                'Read handoff at '+str(handoff)+'; execute task.']
    if provider == 'opencode':
        return ['opencode','run','--model',model,'Read task at '+str(handoff)]
    if provider == 'agy':
        # Integration via the known gjob.py wrapper, NOT undocumented agy flags.
        return ['python3',str(__import__('pathlib').Path(__file__).resolve().parents[1]/'adapters/agy_gjob.py'),'--handoff',str(handoff),'--output',str(output),'--model',model]
    raise ValueError('unknown provider '+provider)
