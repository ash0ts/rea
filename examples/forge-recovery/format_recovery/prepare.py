from __future__ import annotations
import argparse,json,shutil,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'src'))
from fixtures import prepare,CASES
from forge_recovery.common import inventory,write_json,read_json
from forge_recovery.sandbox import Sandbox

def build(root,images):
    prepare(root)
    receipts=[]
    for case in (*CASES,'qualification'):
        out=root/'minify'/case
        with Sandbox(out,root/'source'/case,image=images['build']) as box:
            for name in ('binary.js','reader.js','index.js'):
                r=box.execute(f'node /opt/build/node_modules/terser/bin/terser /input/{name} --compress --mangle --comments false --output /work/{name}')
                if r['exit_code']:raise RuntimeError(r)
        app=root/'inputs'/case/'app';app.mkdir()
        for p in out.glob('*.js'):shutil.copy2(p,app/p.name)
        (app/'package.json').write_text(json.dumps({'name':'offline-record-viewer','version':'1.0.0','main':'index.js','private':True}))
        tests=read_json(root/'oracle'/case/'cases.json')
        oracle_inputs=root/'oracle-check-inputs'/case;shutil.copytree(app,oracle_inputs/'app')
        for t in tests:shutil.copy2(root/'oracle'/case/t['name'],oracle_inputs/t['name'])
        for i in range(2):
            name=f'sample-{i}.bin';shutil.copy2(root/'inputs'/case/name,oracle_inputs/name)
            tests.append({'name':name,'valid':True,'expected':read_json(root/'inputs'/case/f'sample-{i}.json')})
        with Sandbox(root/'oracle-check-work'/case,oracle_inputs,image=images['base']) as box:
            for t in tests:
                r=box.execute(f'node /input/app/index.js /input/{t["name"]}',timeout=5)
                if t['valid']:
                    assert r['exit_code']==0,(case,t['name'],r)
                    assert json.loads(r['stdout'])==t['expected'],(case,t['name'],r,t['expected'])
                else:assert r['exit_code'] not in (0,124,137),(case,t['name'],r)
                receipts.append({'case':case,'name':t['name'],'valid':t['valid'],'execution':r,'matched_independent_expectation':True})
    write_json(root/'oracle-validation.json',receipts)
    write_json(root/'prepared.json',{'inputs':inventory(root/'inputs'),'oracle':inventory(root/'oracle'),'source':inventory(root/'source'),'images':images,'terser':'5.44.1','source_maps_in_agent_inputs':False,'reference_checks':len(receipts),'scope':'Four original laboratory formats plus disjoint qualification; independent Python construction checked against shipped JS readers.'})
    print(json.dumps({'prepared':str(root),'reference_checks':len(receipts)}),flush=True)

if __name__=='__main__':
    import subprocess
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args()
    images=read_json(HERE.parent/'.local/format-recovery-build/retained-images.json')['images']
    build(a.root.resolve(),images)
