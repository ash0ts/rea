from __future__ import annotations
import json, shutil
from pathlib import Path
from forge_recovery.common import canonical_digest, read_json, write_json
from forge_recovery.sandbox import Sandbox

def classify(execution, expected=None):
    if expected is None:
        return {'passed':execution['exit_code'] not in (0,124,137) and bool(execution['stderr'].strip()),'kind':'invalid'}
    actual=None;error=None
    try:actual=json.loads(execution['stdout'])
    except (ValueError,TypeError) as e:error=str(e)
    exact=execution['exit_code']==0 and canonical_digest(actual)==canonical_digest(expected)
    return {'passed':exact,'kind':'valid','actual':actual,'expected':expected,'parse_error':error}

def evaluate(submission:Path, prepared:Path, case:str, root:Path, image:str):
    inputs=root/'input';inputs.mkdir(parents=True)
    work=root/'work';work.mkdir()
    decoder=submission/'decode.py'
    if not decoder.is_file() or decoder.is_symlink():
        return {'passed':False,'behavior_pass':False,'submission_present':False,'valid_passed':0,'valid_total':12,'invalid_passed':0,'invalid_total':7,'cases':[]}
    shutil.copyfile(decoder,work/'decode.py')
    tests=read_json(prepared/'oracle'/case/'cases.json')
    for t in tests:shutil.copyfile(prepared/'oracle'/case/t['name'],inputs/t['name'])
    controls=[]
    for i in range(2):
        name=f'sample-{i}.bin';shutil.copyfile(prepared/'inputs'/case/name,inputs/name)
        controls.append({'name':name,'valid':True,'expected':read_json(prepared/'inputs'/case/f'sample-{i}.json')})
    rows=[]
    with Sandbox(work,inputs,image=image) as box:
        for t in controls+tests:
            execution=box.execute(f'python /work/decode.py /input/{t["name"]}',timeout=5)
            row={'name':t['name'],'execution':execution,**classify(execution,t.get('expected'))}
            rows.append(row)
        resources=box.resources()
    visible=all(r['passed'] for r in rows[:2])
    valid=[r for r in rows[2:] if r['kind']=='valid'];invalid=[r for r in rows[2:] if r['kind']=='invalid']
    result={'passed':all(r['passed'] for r in rows),'behavior_pass':all(r['passed'] for r in valid),
        'submission_present':True,'visible_controls_pass':visible,
        'valid_passed':sum(r['passed'] for r in valid),'valid_total':len(valid),
        'invalid_passed':sum(r['passed'] and visible for r in invalid),'invalid_total':len(invalid),
        'cases':rows,'checker_resources':resources,
        'scope':'Exact JSON behavior on 12 held-out inputs. Seven invalid-input checks require successful visible controls. Python-only checker image has no Node or application artifacts.'}
    write_json(root/'judgment.json',result);return result
