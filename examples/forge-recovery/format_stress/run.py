"""Freeze extra coverage before testing any saved decoder; no inference calls."""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent
sys.path.insert(0, str(EXAMPLE / 'src'))
from fixtures import prepare
from forge_recovery.common import read_json, write_json, inventory, canonical_digest
from forge_recovery.sandbox import Sandbox


def prepare_audit(primary, root):
    if root.exists(): raise ValueError('Use a new audit root; never replace preparation or results')
    if (primary/'stress-audit.json').exists() and read_json(primary/'stress-audit.json')['phase']=='graded':
        raise RuntimeError('A completed audit is already linked; preserve it rather than replace results')
    conf = read_json(primary/'experiment.json'); original = Path(conf['prepared'])
    prepare(root/'inputs'); references = []
    for case in ('chunks', 'journal', 'columns', 'tree'):
        folder = root/'reference'/case
        shutil.copytree(original/'inputs'/case/'app', folder/'input/app')
        tests = read_json(root/'inputs'/case/'cases.json')
        for t in tests: shutil.copyfile(root/'inputs'/case/t['name'], folder/'input'/t['name'])
        with Sandbox(folder/'work', folder/'input', image=conf['images']['base']) as box:
            for t in tests:
                execution = box.execute(f"node /input/app/index.js /input/{t['name']}", timeout=5)
                if t['valid']:
                    assert execution['exit_code'] == 0
                    assert canonical_digest(json.loads(execution['stdout'])) == canonical_digest(t['expected']), (case, t['name'], execution)
                else:
                    assert execution['exit_code'] not in (0, 124, 137) and execution['stderr'].strip(), (case, t['name'], execution)
                references.append(dict(fixture=case, input=t['name'], valid=t['valid'], execution=execution, matched=True))
    write_json(root/'reference-validation.json', references)
    for name in ('run.py', 'fixtures.py', 'RESEARCH.md'):
        (root/'source').mkdir(exist_ok=True)
        shutil.copyfile(HERE/name, root/'source'/name)
    frozen = {'primary_experiment_id': conf['experiment_id'], 'primary_configuration_sha256': conf['configuration_sha256'],
              'primary_root': str(primary), 'inputs': inventory(root/'inputs'), 'source': inventory(root/'source'),
              'reference_validation_sha256': hashlib.sha256((root/'reference-validation.json').read_bytes()).hexdigest(),
              'images': conf['images'], 'attempts': conf['attempts'], 'reference_checks': len(references),
              'scope': 'Post-hoc coverage audit of every saved scored decoder; original scores unchanged; no agent reruns.'}
    frozen['configuration_sha256'] = canonical_digest(frozen)
    write_json(root/'audit.json', frozen)
    write_json(primary/'stress-audit.json', {'path':str(root), 'configuration_sha256':frozen['configuration_sha256'],
                                           'phase':'prepared', 'reference_checks':len(references), 'scope':frozen['scope']})
    return {'prepared_reference_checks': len(references), 'configuration_sha256': frozen['configuration_sha256']}


def grade(primary, root):
    conf = read_json(primary/'experiment.json'); frozen = read_json(root/'audit.json')
    assert frozen['primary_configuration_sha256'] == conf['configuration_sha256']
    assert inventory(root/'inputs') == frozen['inputs'] and inventory(root/'source') == frozen['source']
    assert all(hashlib.sha256((HERE/n).read_bytes()).hexdigest() == h for n, h in frozen['source'].items())
    results = [read_json(primary/'attempts'/s['attempt_id']/'result.json') for s in conf['attempts']]
    assert all(r.get('cleanup_status') == 'complete' and r.get('upload_status') == 'complete' for r in results), 'Wait for the complete frozen campaign'
    if (root/'attempts').exists(): raise RuntimeError('Audit execution exists; reconcile saved checks, never silently replace them')
    summary = []
    for spec in conf['attempts']:
        case = spec['fixture']; folder = root/'attempts'/spec['attempt_id']; inputs = folder/'input'; work = folder/'work'
        inputs.mkdir(parents=True); work.mkdir()
        decoder = primary/'attempts'/spec['attempt_id']/'submission/decode.py'
        result = {**spec, 'primary_configuration_sha256': conf['configuration_sha256'], 'audit_configuration_sha256': frozen['configuration_sha256'],
                  'valid_total': 16, 'invalid_total': 4, 'valid_passed': 0, 'invalid_passed': 0, 'behavior_pass': False,
                  'complete_pass': False, 'submission_present': decoder.is_file(), 'cases': []}
        if decoder.is_file():
            assert not decoder.is_symlink()
            result['submission_sha256'] = hashlib.sha256(decoder.read_bytes()).hexdigest()
            shutil.copyfile(decoder, work/'decode.py')
            tests = []
            original = Path(conf['prepared'])/'inputs'/case
            for i in range(2):
                name = f'sample-{i}.bin'; shutil.copyfile(original/name, inputs/name)
                tests.append(dict(name=name, valid=True, expected=read_json(original/f'sample-{i}.json'), visible=True))
            for t in read_json(root/'inputs'/case/'cases.json'):
                shutil.copyfile(root/'inputs'/case/t['name'], inputs/t['name']); tests.append(t)
            with Sandbox(work, inputs, image=conf['images']['checker']) as box:
                for t in tests:
                    execution = box.execute(f"python /work/decode.py /input/{t['name']}", timeout=5)
                    actual = None; parse_error = None
                    if t['valid']:
                        try: actual = json.loads(execution['stdout'])
                        except (ValueError, TypeError) as error: parse_error = str(error)
                        passed = execution['exit_code'] == 0 and canonical_digest(actual) == canonical_digest(t['expected'])
                    else: passed = execution['exit_code'] not in (0, 124, 137) and bool(execution['stderr'].strip())
                    result['cases'].append(dict(name=t['name'], valid=t['valid'], visible=t.get('visible', False), passed=passed,
                                                expected=t.get('expected'), actual=actual, parse_error=parse_error, execution=execution))
                result['checker_resources'] = box.resources()
            visible = all(c['passed'] for c in result['cases'][:2])
            result['visible_controls_pass'] = visible
            result['valid_passed'] = sum(c['passed'] for c in result['cases'][2:] if c['valid'])
            result['invalid_passed'] = sum(c['passed'] and visible for c in result['cases'][2:] if not c['valid'])
            result['behavior_pass'] = result['valid_passed'] == 16
            result['complete_pass'] = all(c['passed'] for c in result['cases'])
        result['cleanup_status'] = 'complete'
        write_json(folder/'result.json', result); summary.append(result)
        write_json(root/'summary.json', {'configuration_sha256': frozen['configuration_sha256'], 'attempts': summary,
                                        'scope': frozen['scope']})
        print(json.dumps({k:result[k] for k in ('attempt_id','valid_passed','invalid_passed','submission_present')}), flush=True)
    write_json(primary/'stress-audit.json', {'path':str(root), 'configuration_sha256':frozen['configuration_sha256'],
                                           'phase':'graded', 'reference_checks':frozen['reference_checks'],
                                           'audited_attempts':len(summary), 'scope':frozen['scope']})
    return {'audited_attempts': len(summary)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('phase', choices=['prepare', 'grade'])
    parser.add_argument('primary', type=Path); parser.add_argument('root', type=Path); args = parser.parse_args()
    action = prepare_audit if args.phase == 'prepare' else grade
    print(json.dumps(action(args.primary.resolve(), args.root.resolve()), indent=2))
