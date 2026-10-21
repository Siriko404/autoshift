import copy,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.graph import validate,load
root=Path(__file__).resolve().parents[1]
for name in ('g1-production','g2-ralph','g3-pipeline'):
 g=load(root/'examples'/(name+'.json'));assert g['nodes']
g=load(root/'examples/g1-production.json')
assert len([n for n in g['nodes'] if '.audit.plugin.' in n['id']])==2
assert {'workers.item0','workers.item1'}<=set(n['id'] for n in g['nodes'])
raw=json.loads((root/'examples/g1-production.json').read_text())
raw['nodes'][2]['items']=['core']
raw['nodes'][2]['template']['paths']=['src/${item}/**']
wide=validate(raw)
assert len([n for n in wide['nodes'] if '.audit.wide.' in n['id']])==2, 'wide risk rule must create second auditor'
for mutate in ('cycle','duplicate','path','kind','cmd'):
 x=copy.deepcopy(load(root/'examples/g3-pipeline.json'))
 if mutate=='cycle':x['edges'].append({'from':'package','to':'prepare'})
 if mutate=='duplicate':x['nodes'].append(x['nodes'][0])
 if mutate=='path':x['nodes'][0]['paths']=['../../escape']
 if mutate=='kind':x['nodes'][0]['kind']='magic'
 if mutate=='cmd':x['nodes'][0]['cmd']='sh -c true'
 try:validate(x);raise AssertionError('MUTANT SURVIVED '+mutate)
 except ValueError:pass
print('GRAPH_OK')
