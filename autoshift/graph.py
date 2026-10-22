"""Graph compiler and validator. K1 K2 K10; field guideline §1, §2, §8 [S08,S22,S44]."""
import copy
import json
import re
from pathlib import Path

KINDS = {'agent','code','gate','fanout','join','ask','wake'}
OUTCOMES = {'PASS','FAIL','BLOCKED','SKIP'}
NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_.-]{0,90}$')


def load(path):
    return validate(json.loads(Path(path).read_text()))


def validate(g):
    g = copy.deepcopy(g)
    if not isinstance(g, dict) or not isinstance(g.get('nodes'), list) or not g['nodes']:
        raise ValueError('graph needs nodes')
    if not isinstance(g.get('edges', []), list):
        raise ValueError('edges must be a list')
    g.setdefault('edges', [])
    g.setdefault('wip', 2)
    if type(g['wip']) is not int or not 1 <= g['wip'] <= 128:
        raise ValueError('wip out of range')
    # fanout is a static, declarative macro; an actual dynamic plan is a new validated graph version.
    for node in list(g['nodes']):
        if node.get('kind') != 'fanout':
            continue
        items = node.get('items', [])
        template = node.get('template')
        if not isinstance(items, list) or not isinstance(template, dict) or not items:
            raise ValueError('fanout needs items + template')
        dests = [e for e in g['edges'] if e['from'] == node['id']]
        g['edges'] = [e for e in g['edges'] if e not in dests]
        for i, item in enumerate(items):
            child = copy.deepcopy(template)
            child['id'] = '%s.item%s' % (node['id'], i)
            
            for field in ('goal','lane'):
                if field in child: child[field] = str(child[field]).replace('${item}',str(item))
            for field in ('paths','artifacts'):
                if field in child:child[field] = [str(x).replace('${item}',str(item)) for x in child[field]]
            g['nodes'].append(child)
            g['edges'].append({'from': node['id'], 'to':child['id'], 'on':['PASS']})
            for edge in dests:
                g['edges'].append(dict(edge, **{'from': child['id']}))
    # Expansion is data-only; node runners see no project-specific risk rules.
    def first_gate(start):
        # Auditors run AFTER the gate that judges the worker: nearest gate reachable from the worker.
        seen={start};todo=[start]
        while todo:
            cur=todo.pop(0)
            for e in g['edges']:
                if e['from']==cur and e['to'] not in seen:
                    seen.add(e['to']);todo.append(e['to'])
                    if any(x['id']==e['to'] and x.get('kind')=='gate' for x in g['nodes']):return e['to']
        return start
    for rule in g.get('audit_policy', []):
        match = rule.get('patterns', [])
        source_ids = [n['id'] for n in list(g['nodes']) if n.get('kind') == 'agent'
                      and n.get('role', '') == 'worker'
                      and any(overlaps(p, q) for p in match for q in n.get('paths', []))]
        originals = {};tails = {}
        for source in source_ids:
            anchor = rule.get('after') or first_gate(source)
            # All sources sharing an anchor share its onward edges: every chain must APPROVE before they run.
            originals.setdefault(anchor,[e for e in g['edges'] if e['from'] == anchor and 'PASS' in e.get('on', ['PASS'])])
            prev = anchor
            for idx, auditor in enumerate(rule.get('auditors', [])):
                clone = copy.deepcopy(auditor)
                clone['id'] = '%s.audit.%s.%s' % (source, rule['id'], idx+1)
                clone['role'] = 'audit'
                clone.setdefault('kind', 'agent')
                clone.setdefault('lane', 'audit.'+source)
                clone.setdefault('paths', [])
                g['nodes'].append(clone)
                g['edges'].append({'from': prev, 'to':clone['id'], 'on':['PASS']})
                prev = clone['id']
            tails.setdefault(anchor,[]).append(prev)
        for anchor,edges in originals.items():
            for edge in edges:
                g['edges'].remove(edge)
                for tail in tails[anchor]:g['edges'].append(dict(edge, **{'from': tail}))
    ids = set()
    for n in g['nodes']:
        if not isinstance(n, dict) or not NAME.fullmatch(str(n.get('id', ''))):
            raise ValueError('bad node id')
        if n['id'] in ids:
            raise ValueError('duplicate node id')
        ids.add(n['id'])
        if n.get('kind') not in KINDS:
            raise ValueError('unknown node kind')
        # Explicit in shipped graphs; older caller graphs normalised for compatibility.
        expected='judgment' if n['kind']=='agent' else 'deterministic'
        n.setdefault('determinism',expected)
        if n['determinism'] != expected:raise ValueError('node kind contradicts determinism')
        n.setdefault('reasoning','low' if n.get('role')=='worker' else 'high' if n.get('role')=='planner' else 'med' if n['kind']=='agent' else 'low')
        if n['reasoning'] not in ('low','med','high'):raise ValueError('reasoning must be low/med/high')
        if n['kind']=='agent':
            from .doctrine import WORK_PATTERNS
            n.setdefault('work_pattern','verify-and-stop' if n.get('role')=='audit' else 'investigate-first' if n.get('role')=='planner' else 'lean-build')
            if n['work_pattern'] not in WORK_PATTERNS:raise ValueError('unknown work pattern')
            for tier in n.get('tiers',[]):
                if not ((isinstance(tier,dict) and tier.get('provider') and tier.get('model'))
                        or (isinstance(tier,str) and tier)):
                    raise ValueError('agent tier requires owner-configured provider and model')
        if not NAME.fullmatch(n.get('lane', 'default')):
            raise ValueError('invalid lane')
        if 'host' in n and (n['kind']!='code' or n.get('sandbox') or not isinstance(n['host'],dict)):
            raise ValueError('host is only for a code step without a sandbox, and must be an object')
        if n.get('kind') in ('code', 'gate') and not (n.get('kind')=='code' and n.get('host')) and (not isinstance(n.get('cmd'), list) or not n['cmd'] or not all(isinstance(c, str) for c in n['cmd'])):
            raise ValueError('code/gate command requires argv list')
        if n['kind'] == 'agent' and not n.get('tiers'):
            raise ValueError('agent needs tiers')
        for k in ('paths','artifacts'):
            if not isinstance(n.get(k, []), list):
                raise ValueError(k+' needs list')
            if any(not isinstance(x,str) or x.startswith('/') or '..' in Path(x).parts for x in n.get(k, [])):
                raise ValueError('paths must stay relative to workdir')
        if n.get('timeout', 300) <= 0 or n.get('max_attempts', 1) < 1:
            raise ValueError('invalid timeout/attempts')
    # An agent must not execute a worker-authored verifier. A gate's entry
    # is a declared, read-only resource, never a command loaded from --repo.
    if any(n['kind']=='agent' for n in g['nodes']):
        for n in g['nodes']:
            if n['kind']=='gate' and not (isinstance(n.get('trusted_gate'),dict) and n['trusted_gate'].get('entry')):
                raise ValueError('untrusted gate: trusted_gate.entry required when agents are present')
    for n in g['nodes']:
        if (n['kind']=='gate' and n.get('trusted_gate')) or (n['kind']=='code' and n.get('host')):
            t=n['trusted_gate'] if n['kind']=='gate' else n['host']
            if not isinstance(t,dict) or not isinstance(t.get('entry'),str) or not t['entry'] or '..' in Path(t['entry']).parts:
                raise ValueError('bad trusted gate entry')
            if not isinstance(t.get('code_paths',[]),list):raise ValueError('gate code_paths must be an explicit list')
            if not isinstance(t.get('env',[]),list) or any(not isinstance(x,str) or not re.fullmatch(r'[A-Z_][A-Z0-9_]*',x) for x in t.get('env',[])):
                raise ValueError('trusted gate env must list variable names to pass through')
            for key in ('pin','args'):
                if not isinstance(t.get(key,[]),list) or any(not isinstance(x,str) for x in t.get(key,[])):
                    raise ValueError('trusted gate %s must be a list of strings'%key)
            if any(Path(x).is_absolute() or '..' in Path(x).parts for x in t.get('pin',[])):
                raise ValueError('trusted gate pin must stay below the root')
            for codepath in t.get('code_paths',[]):
                bits=Path(codepath).parts
                if (not isinstance(codepath,str) or Path(codepath).is_absolute() or '..' in bits
                        or any(x in ('test','tests','gate','harness','.git','tools') for x in bits)):
                    raise ValueError('gate code_paths may contain code under test, never validators')
            if t.get('root') not in ('@package',) and not Path(t.get('root','')).is_absolute():
                raise ValueError('trusted gate requires absolute root outside worktree')
    for e in g['edges']:
        if e.get('from') not in ids or e.get('to') not in ids or e['from'] == e['to']:
            raise ValueError('edge endpoint invalid')
        if not set(e.get('on',['PASS'])) <= OUTCOMES or not e.get('on',['PASS']):
            raise ValueError('invalid edge outcome')
    # Cycles require explicit unrolling into a finite graph; no hidden forever loops.
    parents = {x:set() for x in ids}
    for e in g['edges']:
        parents[e['to']].add(e['from'])
    emitted = set()
    while True:
        newly = {i for i, p in parents.items() if i not in emitted and p <= emitted}
        if not newly: break
        emitted |= newly
    if emitted != ids:
        raise ValueError('cycle detected: unroll bounded loop explicitly')
    return g


def overlaps(a, b):
    if a == b or a in ('**', '*') or b in ('**', '*'):
        return True
    def prefix(s):
        m = re.search(r'[?*\[]', s)
        return (s[:m.start()] if m else s).rstrip('/')
    x,y = prefix(a),prefix(b)
    return x.startswith(y+'/') or y.startswith(x+'/') or x == y or (not x or not y)


def byid(g):
    return {n['id']:n for n in g['nodes']}
