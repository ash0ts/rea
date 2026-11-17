"""A separately frozen post-hoc Unicode-ordering probe; no inference or repairs."""
import argparse
import hashlib
import json
import shutil
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from forge_recovery.common import read_json, write_json, inventory, canonical_digest
from forge_recovery.sandbox import Sandbox


def cases():
    # These two names sort oppositely under UTF-16 units and Unicode code points.
    rows = [dict(id=1, label='😀', value=17, active=True),
            dict(id=2, label='ｶ', value=-29, active=True)]
    assert [r['id'] for r in sorted(rows, key=lambda r:r['label'])] == [2, 1]
    assert [r['id'] for r in sorted(rows, key=lambda r:r['label'].encode('utf-16-be'))] == [1, 2]
    for version in (1, 2):
        for reverse in (0, 1):
            body = b''
            for row in reversed(rows):
                name = row['label'].encode('utf-8')
                value = zlib.compress(struct.pack('<i' if version == 1 else '>i', row['value']))
                # All varints in this minimal counterexample fit in one byte.
                assert len(name) < 128 and len(value) < 128
                body += bytes([row['id'], 0, 1, len(name)]) + name + bytes([0, len(value)]) + value
            binary = b'TREE' + struct.pack('<BBHII', version, reverse, 2, len(body), zlib.crc32(body)) + body
            yield dict(name=f'ordering-v{version}-reverse{reverse}.bin',
                       expected={'version':version, 'records':rows[::-1] if reverse else rows}, binary=binary)


def prepare(primary, root):
    if root.exists():raise RuntimeError('Preserve existing preparation; use a fresh output directory')
    previous=read_json(primary/'ordering-probe.json') if (primary/'ordering-probe.json').exists() else None
    if previous and previous['phase']=='graded':raise RuntimeError('Preserve graded checks; use a new experiment for changed checks')
    conf=read_json(primary/'experiment.json');inputs=root/'inputs';inputs.mkdir(parents=True)
    tests=[]
    for case in cases():
        (inputs/case['name']).write_bytes(case.pop('binary'));tests.append(case)
    write_json(inputs/'cases.json',tests)
    ref=root/'reference';shutil.copytree(Path(conf['prepared'])/'inputs/tree/app',ref/'input/app')
    for case in tests:shutil.copyfile(inputs/case['name'],ref/'input'/case['name'])
    observed=[]
    with Sandbox(ref/'work',ref/'input',image=conf['images']['base']) as box:
        for case in tests:
            result=box.execute(f"node /input/app/index.js /input/{case['name']}",timeout=5)
            assert result['exit_code']==0 and canonical_digest(json.loads(result['stdout']))==canonical_digest(case['expected'])
            observed.append(dict(name=case['name'],execution=result,matched=True))
    write_json(root/'reference-validation.json',observed)
    shutil.copyfile(__file__,root/'ordering_probe.py')
    completed=sum((primary/'attempts'/s['attempt_id']/'result.json').exists() and
                  read_json(primary/'attempts'/s['attempt_id']/'result.json').get('upload_status')=='complete'
                  for s in conf['attempts'])
    config={'primary_configuration_sha256':conf['configuration_sha256'],'inputs':inventory(inputs),
            'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'reference_sha256':hashlib.sha256((root/'reference-validation.json').read_bytes()).hexdigest(),
            'designed_after_completed_scored_attempts':completed,
            'previous_ungraded_preparation':previous,
            'attempts':[s for s in conf['attempts'] if s['fixture']=='tree'],
            'scope':'Targeted post-hoc probe prompted by source inspection of the first tree baseline and REA decoders. Four inputs across versions and reverse flags; all nine saved tree attempts, no model reruns or decoder edits. Primary and broader stress scores unchanged.',
            'sources':['https://docs.python.org/3/reference/expressions.html#value-comparisons','https://tc39.es/ecma262/#sec-islessthan']}
    config['configuration_sha256']=canonical_digest(config);write_json(root/'probe.json',config)
    write_json(primary/'ordering-probe.json',dict(path=str(root),phase='prepared',configuration_sha256=config['configuration_sha256']))
    return dict(reference_checks=len(observed),configuration_sha256=config['configuration_sha256'])


def grade(primary,root):
    conf=read_json(primary/'experiment.json');frozen=read_json(root/'probe.json')
    assert conf['configuration_sha256']==frozen['primary_configuration_sha256']
    assert inventory(root/'inputs')==frozen['inputs']
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==frozen['source_sha256']
    assert hashlib.sha256((root/'reference-validation.json').read_bytes()).hexdigest()==frozen['reference_sha256']
    assert all(read_json(primary/'attempts'/s['attempt_id']/'result.json').get('upload_status')=='complete' for s in conf['attempts'])
    if (root/'attempts').exists():raise RuntimeError('Probe execution exists; reconcile instead of replacing it')
    summary=[]
    for spec in frozen['attempts']:
        original=primary/'attempts'/spec['attempt_id'];folder=root/'attempts'/spec['attempt_id'];folder.mkdir(parents=True)
        decoder=original/'submission/decode.py'
        result=dict(**spec,submission_present=decoder.is_file(),passed=False,valid_passed=0,valid_total=4,cases=[])
        if decoder.is_file():
            assert not decoder.is_symlink()
            result['submission_sha256']=hashlib.sha256(decoder.read_bytes()).hexdigest()
            (folder/'work').mkdir();(folder/'input').mkdir();shutil.copyfile(decoder,folder/'work/decode.py')
            tests=read_json(root/'inputs/cases.json')
            for test in tests:shutil.copyfile(root/'inputs'/test['name'],folder/'input'/test['name'])
            with Sandbox(folder/'work',folder/'input',image=conf['images']['checker']) as box:
                for test in tests:
                    execution=box.execute(f"python /work/decode.py /input/{test['name']}",timeout=5)
                    try:actual=json.loads(execution['stdout'])
                    except (ValueError,TypeError):actual=None
                    passed=execution['exit_code']==0 and canonical_digest(actual)==canonical_digest(test['expected'])
                    result['cases'].append(dict(**test,actual=actual,execution=execution,passed=passed))
            result.update(valid_passed=sum(t['passed'] for t in result['cases']),passed=all(t['passed'] for t in result['cases']))
        result['cleanup_status']='complete';write_json(folder/'result.json',result);summary.append(result)
        write_json(root/'summary.json',dict(configuration_sha256=frozen['configuration_sha256'],attempts=summary,scope=frozen['scope']))
        print(json.dumps({k:result[k] for k in ('attempt_id','submission_present','valid_passed')}),flush=True)
    write_json(primary/'ordering-probe.json',dict(path=str(root),phase='graded',configuration_sha256=frozen['configuration_sha256'],audited_attempts=len(summary)))
    return dict(audited_attempts=len(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','grade']);p.add_argument('primary',type=Path);p.add_argument('root',type=Path);a=p.parse_args()
    print(json.dumps((prepare if a.phase=='prepare' else grade)(a.primary.resolve(),a.root.resolve()),indent=2))
