"""Publish the frozen format-recovery comparison and verify saved evidence."""
from __future__ import annotations
import argparse,json,statistics,sys
from collections import Counter
from pathlib import Path
import wandb
from publish_dependency_review import verify_attempt
from publish_dashboard import forge_url

def read(p):return json.loads(p.read_text())
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def sha(p):
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()

def verify_model_history(folder,spans):
    """Match every delivered model context, response and known token count."""
    messages=read(folder/'messages.json');events=read(folder/'events.json');result=read(folder/'result.json')
    by={(s['trace_id'],s['span_id']):s for s in spans}
    assistant_indices=[i for i,m in enumerate(messages) if m['role']=='assistant']
    completed=0;known_input=0;known_output=0;unknown=0;requests=0
    def projected(m):
        parts=[]
        if m.get('content'):parts.append({'type':'text','content':m['content']})
        for c in m.get('tool_calls') or []:
            parts.append({'type':'tool_call','id':c['id'],'name':c['function']['name'],'arguments':c['function']['arguments']})
        if m['role']=='tool':parts=[{'type':'tool_call_response','id':m['tool_call_id'],'response':m['content']}]
        return {'role':m['role'],'parts':parts}
    def stored(values):
        if isinstance(values,str):values=json.loads(values)
        return [{'role':m['role'],'parts':json.loads(m['content']) if isinstance(m['content'],str) else m['content']} for m in values]
    for e in events:
        if e['kind'] not in ('model','model_error'):continue
        requests+=1;s=by[e['trace_id'],e['span_id']]
        endpoint=assistant_indices[completed] if completed<len(assistant_indices) else len(messages)
        assert stored(s['input_messages'])==[projected(m) for m in messages[:endpoint]],(folder.name,'model context',e['request'])
        if e['kind']=='model':
            assert stored(s['output_messages'])==[projected(messages[endpoint])],(folder.name,'model output',e['request'])
            assert s['finish_reasons']==[e['finish_reason']]
            completed+=1
        else:assert s['status_code']=='ERROR'
        usage=e.get('usage')
        if usage:
            assert s['input_tokens']==usage['prompt_tokens'] and s['output_tokens']==usage['completion_tokens']
            known_input+=usage['prompt_tokens'];known_output+=usage['completion_tokens']
        else:unknown+=1
    assert completed==len(assistant_indices)
    assert requests==result['usage']['requests']
    assert (known_input,known_output,unknown)==tuple(result['usage'][k] for k in ('input_tokens','output_tokens','unknown_usage_requests'))
    return {'model_contexts_matched':requests,'model_responses_matched':completed,'requests_with_unknown_usage':unknown}

def exact_json(left,right):
    # Independently check types and structure rather than reuse the grader's digest.
    if type(left) is not type(right):return False
    if isinstance(right,dict):return left.keys()==right.keys() and all(exact_json(left[k],v) for k,v in right.items())
    if isinstance(right,list):return len(left)==len(right) and all(exact_json(a,b) for a,b in zip(left,right))
    return left==right

def verify_judgments(root,conf):
    prepared=Path(conf['prepared']);rows=[]
    for spec in conf['qualification']+conf['attempts']:
        folder=root/'attempts'/spec['attempt_id'];result=read(folder/'result.json');judge=result.get('checker')
        item={'attempt_id':spec['attempt_id']}
        if judge is None:
            item['status']='unavailable';rows.append(item);continue
        if not judge['submission_present']:
            assert not (folder/'submission/decode.py').is_file() or (folder/'submission/decode.py').is_symlink()
            assert not judge['behavior_pass'] and not judge['passed'] and judge['valid_passed']==judge['invalid_passed']==0
            item['status']='missing_program';rows.append(item);continue
        expected={t['name']:t for t in read(prepared/'oracle'/spec['fixture']/'cases.json')}
        for i in range(2):expected[f'sample-{i}.bin']={'valid':True,'expected':read(prepared/'inputs'/spec['fixture']/f'sample-{i}.json')}
        assert len(judge['cases'])==len(expected)==21
        outcomes={}
        for case in judge['cases']:
            reference=expected[case['name']];execution=case['execution']
            if reference['valid']:
                assert exact_json(case['expected'],reference['expected'])
                try:actual=json.loads(execution['stdout'])
                except (ValueError,TypeError):actual=None
                passed=execution['exit_code']==0 and exact_json(actual,reference['expected'])
            else:passed=execution['exit_code'] not in (0,124,137) and bool(execution['stderr'].strip())
            assert passed==case['passed'],(spec['attempt_id'],case['name'])
            outcomes[case['name']]=passed
        assert len(outcomes)==len(expected)
        visible=all(outcomes[f'sample-{i}.bin'] for i in range(2))
        valid=sum(v for n,v in outcomes.items() if expected[n]['valid'] and not n.startswith('sample-'))
        invalid=sum(v and visible for n,v in outcomes.items() if not expected[n]['valid'])
        assert (valid,invalid,visible)==(judge['valid_passed'],judge['invalid_passed'],judge['visible_controls_pass'])
        assert (valid==12)==judge['behavior_pass'] and all(outcomes.values())==judge['passed']
        item.update(status='all_recorded_checks_reconciled',cases=len(outcomes));rows.append(item)
    value={'attempts':rows,'scope':'Independent typed JSON comparison of retained executions against frozen expected data; original judgments unchanged. Reference correctness and descriptive source audit are separate.'}
    write(root/'judgment-integrity.json',value);return value

def verify_evidence_exports(root,conf):
    import re
    rows=[]
    for spec in conf['qualification']+conf['attempts']:
        if spec['arm']!='rea':continue
        folder=root/'attempts'/spec['attempt_id'];result=read(folder/'result.json')
        item={'attempt_id':spec['attempt_id'],'export_status':result.get('evidence_export',{}).get('status','unavailable')}
        if item['export_status']=='complete':
            bundle=folder/'evidence/bundle.json';assert sha(bundle)==result['evidence_export']['sha256']
            exported=read(bundle);ids={r['evidence_id'] for r in exported['records']}
            assert len(ids)==len(exported['records'])
            analysis=folder/'submission/analysis.md'
            quoted=set(re.findall(r'ev_[0-9a-f]{64}',analysis.read_text())) if analysis.exists() else set()
            item.update(canonical_records=len(ids),unknowns=exported['unknowns'],export_sha256=sha(bundle),
                        explanation_present=analysis.exists(),quoted_evidence_ids=sorted(quoted),
                        quoted_ids_missing_from_export=sorted(quoted-ids))
            item['analysis_coverage']=[]
            for record in exported['records']:
                if record['operation']!='analyze_javascript_application':continue
                n=record['normalized_result'];semantic=n['semantic_graph']['coverage']
                item['analysis_coverage'].append({'evidence_id':record['evidence_id'],
                    'artifact_sha256':n['root_artifact_sha256'],'statistics':n['statistics'],
                    'application_graph':n['graph']['coverage'],
                    'semantic_graph':{k:v for k,v in semantic.items() if k!='families'},
                    'semantic_families':[{**{k:v for k,v in family.items() if k!='unknown_ids'},'unknown_count':len(family['unknown_ids'])} for family in semantic['families']]})
        rows.append(item)
    value={'attempts':rows,'scope':'Export hashes and canonical record identity, with missing explanation references retained as findings. This does not validate narrative claims or causal benefit.'}
    write(root/'evidence-integrity.json',value);return value

def verify_stress_judgments(root,conf):
    """Reconcile the separate audit without reusing its scoring implementation."""
    stress=Path(read(root/'stress-audit.json')['path']);frozen=read(stress/'audit.json')
    for directory in ('inputs','source'):
        observed={str(p.relative_to(stress/directory)):sha(p) for p in sorted((stress/directory).rglob('*')) if p.is_file()}
        assert observed==frozen[directory],('stress drift',directory)
    assert sha(stress/'reference-validation.json')==frozen['reference_validation_sha256']
    rows=[]
    for spec in conf['attempts']:
        folder=root/'attempts'/spec['attempt_id'];saved=read(stress/'attempts'/spec['attempt_id']/'result.json')
        assert saved['audit_configuration_sha256']==frozen['configuration_sha256']
        decoder=folder/'submission/decode.py'
        if not saved['submission_present']:
            assert not decoder.exists() and not saved['cases']
            assert not saved['behavior_pass'] and not saved['complete_pass']
            rows.append({'attempt_id':spec['attempt_id'],'status':'missing_program'});continue
        assert not decoder.is_symlink() and sha(decoder)==saved['submission_sha256']
        expected={t['name']:t for t in read(stress/'inputs'/spec['fixture']/'cases.json')}
        for i in range(2):expected[f'sample-{i}.bin']={'valid':True,'expected':read(Path(conf['prepared'])/'inputs'/spec['fixture']/f'sample-{i}.json')}
        assert len(saved['cases'])==len(expected)==22
        outcomes={}
        for case in saved['cases']:
            reference=expected[case['name']];execution=case['execution']
            assert case['valid']==reference['valid']
            if reference['valid']:
                assert exact_json(case['expected'],reference['expected'])
                try:actual=json.loads(execution['stdout'])
                except (ValueError,TypeError):actual=None
                assert exact_json(actual,case['actual'])
                passed=execution['exit_code']==0 and exact_json(actual,reference['expected'])
            else:passed=execution['exit_code'] not in (0,124,137) and bool(execution['stderr'].strip())
            assert passed==case['passed'],(spec['attempt_id'],case['name'])
            outcomes[case['name']]=passed
        assert len(outcomes)==22
        visible=all(outcomes[f'sample-{i}.bin'] for i in range(2))
        valid=sum(v for n,v in outcomes.items() if expected[n]['valid'] and not n.startswith('sample-'))
        invalid=sum(v and visible for n,v in outcomes.items() if not expected[n]['valid'])
        assert (visible,valid,invalid)==(saved['visible_controls_pass'],saved['valid_passed'],saved['invalid_passed'])
        assert (valid==16)==saved['behavior_pass'] and all(outcomes.values())==saved['complete_pass']
        rows.append({'attempt_id':spec['attempt_id'],'status':'all_recorded_checks_reconciled','cases':22})
    value={'attempts':rows,'scope':'Separate typed JSON reconciliation of every retained post-hoc execution; primary and audit scores unchanged.'}
    write(root/'stress-judgment-integrity.json',value);return value

def verify_inputs(root,conf):
    prepared=Path(conf['prepared']);checks=[]
    def inventory(path):return {str(p.relative_to(path)):sha(p) for p in sorted(path.rglob('*')) if p.is_file()}
    for kind in ('inputs','oracle','source'):
        assert inventory(prepared/kind)==conf['prepared_manifest'][kind],('prepared drift',kind)
    for spec in conf['qualification']+conf['attempts']:
        folder=root/'attempts'/spec['attempt_id'];prefix=spec['fixture']+'/'
        expected={n[len(prefix):]:h for n,h in conf['prepared_manifest']['inputs'].items() if n.startswith(prefix)}
        if spec['arm']=='data_only':expected={n:h for n,h in expected.items() if not n.startswith('app/')}
        assert inventory(folder/'input')==expected,(spec['attempt_id'],'input files differ')
        assert read(folder/'result.json')['input_sha256']==expected
        assert not any(n.endswith('.map') or n.startswith(('oracle/','source/')) for n in expected)
        checks.append({'attempt_id':spec['attempt_id'],'input_files':len(expected),'application_present':any(n.startswith('app/') for n in expected),'exact_frozen_inventory_match':True})
    value={'attempts':checks,'prepared_inputs_oracle_source_unchanged':True,
           'scope':'Exact staged file inventory and hashes. Live mount and credential isolation are documented separately in live-sandbox-check.json.'}
    write(root/'input-integrity.json',value);return value

def verify_ordering_probe(root,conf):
    probe=Path(read(root/'ordering-probe.json')['path']);frozen=read(probe/'probe.json')
    assert sha(probe/'ordering_probe.py')==frozen['source_sha256']
    assert sha(probe/'reference-validation.json')==frozen['reference_sha256']
    assert {str(p.relative_to(probe/'inputs')):sha(p) for p in (probe/'inputs').iterdir()}==frozen['inputs']
    tests={t['name']:t for t in read(probe/'inputs/cases.json')};rows=[]
    for spec in frozen['attempts']:
        folder=probe/'attempts'/spec['attempt_id'];saved=read(folder/'result.json')
        decoder=root/'attempts'/spec['attempt_id']/'submission/decode.py'
        assert saved['cleanup_status']=='complete'
        if not saved['submission_present']:
            assert not decoder.exists() and not saved['cases'] and not saved['passed']
            rows.append({'attempt_id':spec['attempt_id'],'status':'missing_program'});continue
        assert not decoder.is_symlink() and sha(decoder)==saved['submission_sha256']
        staged={p.name:sha(p) for p in (folder/'input').iterdir()}
        assert staged=={n:frozen['inputs'][n] for n in tests},'Expected answers must remain outside the checker mount'
        outcomes=[]
        assert {t['name'] for t in saved['cases']}==set(tests) and len(saved['cases'])==4
        for case in saved['cases']:
            expected=tests[case['name']]['expected'];execution=case['execution']
            try:actual=json.loads(execution['stdout'])
            except (ValueError,TypeError):actual=None
            passed=execution['exit_code']==0 and exact_json(actual,expected)
            assert exact_json(expected,case['expected']) and exact_json(actual,case['actual']) and passed==case['passed']
            outcomes.append(passed)
        assert sum(outcomes)==saved['valid_passed'] and all(outcomes)==saved['passed']
        rows.append({'attempt_id':spec['attempt_id'],'status':'all_recorded_checks_reconciled','cases':4})
    value={'attempts':rows,'scope':frozen['scope']};write(root/'ordering-judgment-integrity.json',value);return value

def verify_controls(root,conf):
    checks=[]
    for spec in conf['qualification']+conf['attempts']:
        folder=root/'attempts'/spec['attempt_id']
        spans=read(folder/'lens-readback.json')['spans']
        models=[s for s in spans if s['operation_name']=='chat']
        for s in models:
            assert s['request_model']==conf['model']
            assert not s['response_model'] or s['response_model']==conf['model']
            assert s['request_temperature']==conf['temperature'] and s['request_max_tokens']==conf['request_max_tokens']
            attributes=json.loads(s['raw_span_dump'])['attributes']
            schemas=attributes['recovery']['tool_definitions']
            schemas=json.loads(schemas) if isinstance(schemas,str) else schemas
            assert schemas==conf['tools']['rea' if spec['arm']=='rea' else 'baseline']
            messages=json.loads(s['input_messages']) if isinstance(s['input_messages'],str) else s['input_messages']
            assert len(messages)>=2
            for m,role,key in zip(messages[:2],('system','user'),('system_prompt','task_prompt')):
                assert m['role']==role
                parts=json.loads(m['content'])
                assert parts==[{'type':'text','content':conf[key]}]
        checks.append({'attempt_id':spec['attempt_id'],'model_requests_checked':len(models),
                       **verify_model_history(folder,spans),
                       'verified':['requested and returned model identity','temperature and output limit','actual tool schemas in raw span','identical system and task prompts']})
    write(root/'control-integrity.json',checks)
    return checks

def derive(root):
    conf=read(root/'experiment.json');summary=read(root/'summary.json');rows=summary['attempts']
    assert len(rows)==len(conf['attempts'])==36
    assert {r['attempt_id'] for r in rows}=={s['attempt_id'] for s in conf['attempts']}
    stress_meta=read(root/'stress-audit.json')
    assert stress_meta['phase']=='graded','Finish the separately frozen stress audit before publishing'
    stress_root=Path(stress_meta['path']);stress_config=read(stress_root/'audit.json');stress_summary=read(stress_root/'summary.json')
    assert stress_meta['configuration_sha256']==stress_config['configuration_sha256']==stress_summary['configuration_sha256']
    stress={r['attempt_id']:r for r in stress_summary['attempts']}
    assert set(stress)=={r['attempt_id'] for r in rows} and len(stress_summary['attempts'])==36
    probe_meta=read(root/'ordering-probe.json');assert probe_meta['phase']=='graded'
    probe_root=Path(probe_meta['path']);probe_conf=read(probe_root/'probe.json');probe_summary=read(probe_root/'summary.json')
    assert probe_meta['configuration_sha256']==probe_conf['configuration_sha256']==probe_summary['configuration_sha256']
    probe={r['attempt_id']:r for r in probe_summary['attempts']}
    assert len(probe_summary['attempts'])==9 and set(probe)=={s['attempt_id'] for s in conf['attempts'] if s['fixture']=='tree'}
    measurements=[]
    for r in rows:
        folder=root/'attempts'/r['attempt_id'];events=read(folder/'events.json');c=r.get('checker',{});u=r['usage']
        spans=read(folder/'lens-readback.json')['spans']
        rea_tools=[v for v in spans if v['operation_name']=='execute_tool' and v['tool_name']!='execute']
        successful=[v for v in rea_tools if v['status_code']!='ERROR' and v['ended_at']]
        focused=('trace_application_feature','trace_javascript_semantics','inspect_analysis_view')
        resources=r.get('agent_resources',{});extra=stress[r['attempt_id']]
        decoder=folder/'submission/decode.py'
        assert extra['submission_present']==decoder.is_file()
        if decoder.is_file():assert sha(decoder)==extra['submission_sha256'],'Stress audit changed submitted bytes'
        measurements.append({'attempt_id':r['attempt_id'],'fixture':r['fixture'],'arm':r['arm'],'repetition':r['repetition'],
            'recorded_attempt':1,'checks_available':int('passed' in c),'behavior_pass':c.get('behavior_pass'),'complete_pass':c.get('passed'),
            'stress_behavior_pass':extra['behavior_pass'],'stress_complete_pass':extra['complete_pass'],
            'stress_valid_passed':extra['valid_passed'],'stress_invalid_passed':extra['invalid_passed'],
            'ordering_probe_valid_passed':probe[r['attempt_id']]['valid_passed'] if r['attempt_id'] in probe else None,
            'valid_passed':c.get('valid_passed'),'valid_total':c.get('valid_total'),'invalid_passed':c.get('invalid_passed'),'invalid_total':c.get('invalid_total'),
            'task_tokens':u['input_tokens']+u['output_tokens'] if u['unknown_usage_requests']==0 else None,
            'reported_tokens_lower_bound':u['input_tokens']+u['output_tokens'],
            'unknown_usage_requests':u['unknown_usage_requests'],
            'token_total_available':int(u['unknown_usage_requests']==0),
            'model_requests':u['requests'],
            'output_truncated':any(e.get('finish_reason')=='length' for e in events if e['kind']=='model'),
            'agent_seconds':r['agent_elapsed_seconds'],'conservative_cost_estimate_usd':u['reserved_or_estimated_usd'],
            'rea_calls':len(rea_tools),
            'focused_rea_calls':sum(v['tool_name'] in focused for v in rea_tools),
            'successful_application_analyses':sum(v['tool_name']=='analyze_javascript_application' for v in successful),
            'successful_focused_queries':sum(v['tool_name'] in focused for v in successful),
            'rea_error_spans':sum(v['status_code']=='ERROR' for v in rea_tools),
            'evidence_bytes':sum(p.stat().st_size for p in (folder/'evidence').glob('*')),
            'evidence_export_status':r.get('evidence_export',{}).get('status','unavailable'),
            'analysis_present':(folder/'submission/analysis.md').is_file(),
            'container_cpu_seconds':resources.get('container_cpu_seconds'),'container_peak_memory_bytes':resources.get('container_peak_memory_bytes'),
            'task_status':r['task_status'],'lens_url':r['lens_url'],'artifact':r.get('publication',{}).get('artifact'),
            'run_url':r.get('publication',{}).get('run_url')})
    pairs=[]
    for case in dict.fromkeys(m['fixture'] for m in measurements):
        for rep in (1,2,3):
            group={m['arm']:m for m in measurements if m['fixture']==case and m['repetition']==rep}
            b,t=group['baseline']['behavior_pass'],group['rea']['behavior_pass']
            outcome='unavailable' if b is None or t is None else 'both_pass' if b and t else 'both_fail' if not b and not t else 'rea_only' if t else 'baseline_only'
            sb,st=group['baseline']['stress_behavior_pass'],group['rea']['stress_behavior_pass']
            extra_outcome='both_pass' if sb and st else 'both_fail' if not sb and not st else 'rea_only' if st else 'baseline_only'
            pairs.append({'fixture':case,'repetition':rep,'outcome':outcome,'stress_outcome':extra_outcome,'arms':group})
    comparison={'stress_audit':{'configuration_sha256':stress_config['configuration_sha256'],'scope':stress_config['scope'],'reference_checks':stress_config['reference_checks']},'experiment_id':conf['experiment_id'],'configuration_sha256':conf['configuration_sha256'],'measurements':measurements,'pairs':pairs,
        'paired_outcomes':dict(Counter(p['outcome'] for p in pairs)),
        'stress_paired_outcomes':dict(Counter(p['stress_outcome'] for p in pairs)),
        'arms':{arm:{'attempts':sum(m['arm']==arm for m in measurements),'judged':sum(m['arm']==arm and m['behavior_pass'] is not None for m in measurements),'behavior_passes':sum(m['arm']==arm and m['behavior_pass'] is True for m in measurements),'complete_passes':sum(m['arm']==arm and m['complete_pass'] is True for m in measurements),'explanations_saved':sum(m['arm']==arm and m['analysis_present'] for m in measurements),'stress_behavior_passes':sum(m['arm']==arm and m['stress_behavior_pass'] for m in measurements),'stress_complete_passes':sum(m['arm']==arm and m['stress_complete_pass'] for m in measurements)} for arm in ('baseline','rea','data_only')},
        'scope':'Four original laboratory formats, three repeats, one model. Data-only is a diagnostic arm. No population superiority or human-productivity claim.'}
    resources={}
    for arm in ('baseline','rea','data_only'):
        selected=[m for m in measurements if m['arm']==arm]
        values={'stop_statuses':dict(Counter(m['task_status'] for m in selected)),
                'requests_with_unknown_usage':sum(m['unknown_usage_requests'] for m in selected)}
        for metric in ('task_tokens','reported_tokens_lower_bound','agent_seconds','conservative_cost_estimate_usd','container_cpu_seconds','container_peak_memory_bytes'):
            available=[m[metric] for m in selected if m[metric] is not None]
            values[metric]={'available_attempts':len(available),'sum':sum(available) if available and metric!='container_peak_memory_bytes' else None,
                            'median':statistics.median(available) if available else None}
        resources[arm]=values
    paired_resources={}
    for metric in ('task_tokens','agent_seconds','container_cpu_seconds','container_peak_memory_bytes'):
        available=[p for p in pairs if all(p['arms'][a][metric] is not None for a in ('baseline','rea'))]
        ratios=[p['arms']['rea'][metric]/p['arms']['baseline'][metric] for p in available if p['arms']['baseline'][metric]>0]
        paired_resources[metric]={'available_pairs':len(available),
            'rea_higher':sum(p['arms']['rea'][metric]>p['arms']['baseline'][metric] for p in available),
            'rea_lower':sum(p['arms']['rea'][metric]<p['arms']['baseline'][metric] for p in available),
            'rea_equal':sum(p['arms']['rea'][metric]==p['arms']['baseline'][metric] for p in available),
            'median_ratio':statistics.median(ratios) if ratios else None,
            'minimum_ratio':min(ratios) if ratios else None,'maximum_ratio':max(ratios) if ratios else None}
    comparison['resources']={'arms':resources,'paired':paired_resources,
        'scope':'Descriptive measurements, all attempts retained. Sums over available values have explicit coverage; process-family memory peaks are not added. Repeated context and schemas are included in task tokens. Inference CPU/memory and settled billing are unavailable.'}
    comparison['ordering_probe']={'configuration_sha256':probe_conf['configuration_sha256'],'scope':probe_conf['scope'],
        'designed_after_completed_scored_attempts':probe_conf['designed_after_completed_scored_attempts'],
        'arms':{arm:{'attempts':3,'submissions':sum(r['arm']==arm and r['submission_present'] for r in probe.values()),
                     'passes':sum(r['arm']==arm and r['passed'] for r in probe.values())} for arm in ('baseline','rea','data_only')}}
    write(root/'comparison.json',comparison);return comparison

def publish(root):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
    from forge_recovery.telemetry import credentials,ensure_private_project
    credentials();ensure_private_project('wandb')
    import wandb_workspaces.reports.v2 as wr
    from wandb_workspaces import expr
    if (root/'publication.json').exists():return read(root/'publication.json')
    if (root/'publication-progress.json').exists():raise RuntimeError('Publication needs reconciliation before retry')
    conf=read(root/'experiment.json');comp=derive(root);eid=conf['experiment_id']
    audit=[verify_attempt(root/'attempts'/s['attempt_id']) for s in conf['qualification']+conf['attempts']]
    verify_controls(root,conf);verify_inputs(root,conf);verify_evidence_exports(root,conf);verify_judgments(root,conf);verify_stress_judgments(root,conf);verify_ordering_probe(root,conf)
    write(root/'lens-integrity.json',{'attempts':audit,'scope':'Actual messages, tool IDs, arguments, results and parentage; causal support audited separately.'})
    api=wandb.Api(timeout=60)
    for m in comp['measurements']:
        values={k:v for k,v in m.items() if k not in ('attempt_id','fixture','arm','repetition')}
        for key in ('behavior_pass','complete_pass'):values[key]=int(values[key]) if values[key] is not None else None
        run=api.run('wandb/rea-showcase/'+m['attempt_id'])
        display=f"{m['fixture']} · {m['arm']} · {m['repetition']}"
        run.name=display;run.update();run.summary.update(values)
        saved=api.run('wandb/rea-showcase/'+m['attempt_id']);observed=dict(saved.summary)
        assert saved.name==display and all(observed.get(k)==v for k,v in values.items()),m['attempt_id']
    selected=api.runs('wandb/rea-showcase',filters={'config.experiment_id':eid,'config.phase':'scored'})
    assert {r.id for r in selected}=={s['attempt_id'] for s in conf['attempts']},'Native run filter does not match the frozen scored set'
    files={}
    for name in ('experiment.json','qualification.json','summary.json','comparison.json','budget.json','lens-integrity.json','control-integrity.json','input-integrity.json','reference-integrity.json','judgment-integrity.json','stress-judgment-integrity.json','ordering-judgment-integrity.json','evidence-integrity.json','live-sandbox-check.json','semantic-audit.json','artifact-sizes.json','submission-inventory.json','cleanup-summary.json','maintenance-validation.json','stress-audit.json','ordering-probe.json'):
        if (root/name).exists():files[name]=root/name
    prepared=Path(conf['prepared'])
    for base,prefix in ((prepared/'inputs','prepared/inputs'),(prepared/'oracle','prepared/oracle'),(prepared/'source','prepared/source'),(root/'frozen-source','source'),(root/'build-environment','build-environment'),(root/'post-run-maintenance','post-run-maintenance'),(root/'preparation-history','preparation-history'),(root/'media','media')):
        for p in base.rglob('*'):
            if p.is_file():files[prefix+'/'+str(p.relative_to(base))]=p
    for name in ('prepared.json','oracle-validation.json'):files['prepared/'+name]=prepared/name
    for p in prepared.rglob('*.container.json'):files['prepared/'+str(p.relative_to(prepared))]=p
    build=root.parent/'format-recovery-build'
    files['build-retention/retained-images.json']=build/'retained-images.json'
    for p in (build/'retention').glob('*.container.json'):files['build-retention/'+p.name]=p
    stress_root=Path(read(root/'stress-audit.json')['path'])
    for name in ('audit.json','summary.json','reference-validation.json','preparation-history.json'):
        files['stress/'+name]=stress_root/name
    for sub in ('inputs','source','coverage-validation'):
        for p in (stress_root/sub).rglob('*'):
            if p.is_file():files['stress/'+str(p.relative_to(stress_root))]=p
    for p in stress_root.rglob('*.container.json'):files['stress/'+str(p.relative_to(stress_root))]=p
    for p in (stress_root/'attempts').glob('*/result.json'):files['stress/'+str(p.relative_to(stress_root))]=p
    probe_root=Path(read(root/'ordering-probe.json')['path'])
    for name in ('probe.json','summary.json','reference-validation.json','ordering_probe.py','preparation-history.json'):
        files['ordering-probe/'+name]=probe_root/name
    for sub in ('inputs','preparation-history'):
        for p in (probe_root/sub).rglob('*'):
            if p.is_file():files['ordering-probe/'+str(p.relative_to(probe_root))]=p
    for p in probe_root.rglob('*.container.json'):files['ordering-probe/'+str(p.relative_to(probe_root))]=p
    for p in (probe_root/'attempts').glob('*/result.json'):files['ordering-probe/'+str(p.relative_to(probe_root))]=p
    for spec in conf['qualification']+conf['attempts']:
        folder=root/'attempts'/spec['attempt_id'];r=read(folder/'result.json')
        assert r['cleanup_status']=='complete' and r['upload_status']=='complete'
        for name in ('result.json','messages.json','events.json','lens-readback.json'):
            if (folder/name).exists():files[str((folder/name).relative_to(root))]=folder/name
        for sub in ('submission','evidence'):
            for p in (folder/sub).rglob('*'):
                if p.is_file():files[str(p.relative_to(root))]=p
        judgment=folder/'checks/judgment.json'
        if judgment.exists():files[str(judgment.relative_to(root))]=judgment
    for p in root.rglob('*.container.json'):files[str(p.relative_to(root))]=p
    for rel,digest in conf['code'].items():assert sha(root/'frozen-source'/rel)==digest,rel
    contract=Path(__file__).resolve().parents[1]/'format_recovery/RESEARCH.md'
    assert sha(contract)==conf['research_contract_sha256'];files['source/format_recovery/RESEARCH.md']=contract
    for name in ('publish_format_recovery.py','build_format_media.py','build_format_example.py','publish_format_media.py'):
        files['publication-source/'+name]=Path(__file__).resolve().parent/name
    manifest={n:sha(p) for n,p in files.items()};write(root/'evidence-manifest.json',manifest);files['evidence-manifest.json']=root/'evidence-manifest.json'
    progress={'experiment_id':eid,'state':'publishing'};write(root/'publication-progress.json',progress)
    with wandb.init(entity='wandb',project='rea-showcase',id=eid+'-evidence',job_type='format-recovery-evidence',dir=str(root),settings=wandb.Settings(disable_git=True,disable_code=True,console='off')) as run:
        artifact=wandb.Artifact(eid+'-evidence',type='format-recovery-evidence',metadata={'configuration_sha256':conf['configuration_sha256'],'scored_attempts':36})
        for n,p in files.items():artifact.add_file(str(p),name=n)
        a=run.log_artifact(artifact).wait();progress.update(artifact=f'wandb/rea-showcase/{a.name}',artifact_digest=a.digest);write(root/'publication-progress.json',progress)
    downloaded=Path(api.artifact(progress['artifact']).download(root=str(root/'artifact-readback')))
    assert all(sha(downloaded/n)==h for n,h in manifest.items())
    assert sha(downloaded/'evidence-manifest.json')==sha(root/'evidence-manifest.json')
    artifact_name,version=progress['artifact'].rsplit('/',1)[1].split(':')
    progress.update(verified_files=len(manifest),artifact_url=f'https://forge.coreweave.com/wandb/wandb/rea-showcase/artifacts/format-recovery-evidence/{artifact_name}/{version}/files')
    write(root/'publication-progress.json',progress)
    nav=['| Format | Repeat | Arm | Primary valid / 12 | Added valid / 16 | Tree ordering / 4 | All primary functional checks | Explanation saved | Stop status | Trace |','|---|---:|---|---:|---:|---:|---|---|---|---|']
    for m in comp['measurements']:
        stop=m['task_status']+(' (output truncated)' if m['output_truncated'] else '')
        nav.append(f"| {m['fixture']} | {m['repetition']} | {m['arm']} | {m['valid_passed'] if m['valid_passed'] is not None else 'Unavailable'} | {m['stress_valid_passed']} | {m['ordering_probe_valid_passed'] if m['fixture']=='tree' else 'Not applicable'} | {m['complete_pass']} | {m['analysis_present']} | {stop} | [Agent Lens]({m['lens_url']}) · [Run / files]({m['run_url']}) |")
    intro=f'''## Recover behavior, then compare tools

Four original offline binary formats, three attempts per arm, 36 scored attempts. The primary comparison gives the same model the shipped minified application and ordinary tools, with or without a guided REA workflow. A sample-only arm tests whether the artifact contributes information; it is not the headline baseline. Separate Python construction and JavaScript execution agreed on all 105 reference checks before scoring. Every submission runs in a Python-only isolated checker with no original application or prior outputs.

Primary success requires exact outputs on all 12 held-out inputs. The all-functional-checks column additionally includes two visible controls and seven invalid-input cases. Tool invocation and explanation are not functional points. A passing decoder can coexist with a budget stop or missing analysis document; these remain in the evidence. Four related laboratory tasks and three repetitions do not establish general superiority. Tokens include schemas and repeated context; costs are conservative estimates, not billing. Agent elapsed time includes sandbox setup, Evidence export and cleanup; grading and publication are outside that metric. All scored outcomes remain, including budget stops.

Paired primary outcomes: `{json.dumps(comp['paired_outcomes'],sort_keys=True)}`. Complete counts and source records are below.
'''
    intro+='''
## Separate post-hoc coverage audit

The primary generator left some relationships correlated, including chunk record IDs and logical order. After twelve scored attempts had completed, we designed additional inputs without changing the primary protocol: sixteen valid files and four format-specific malformed inputs per family. These cross version/flag conditions and vary chunk IDs independently of slots, transaction histories, column/bitmap boundaries, and ancestor visibility. All eighty expectations were checked against the frozen original reader before any saved decoder received them. Two corpus-coverage regressions also passed. Every saved scored decoder is included, with no inference reruns or edits.

The added-input results are a post-hoc generalization audit, not preregistered primary scores or additional independent agent trials. Original results remain unchanged. The same saved program, exact-JSON criteria, visible rejection controls and Python-only isolation are used. Full preparation history, including a fixed pre-grading coverage regression, is retained.
'''
    totals=['| Arm | Primary valid pass | All primary checks | Added valid pass | All added checks | Explanation saved |','|---|---:|---:|---:|---:|---:|']
    for arm,v in comp['arms'].items():
        totals.append(f"| {arm} | {v['behavior_passes']}/12 | {v['complete_passes']}/12 | {v['stress_behavior_passes']}/12 | {v['stress_complete_passes']}/12 | {v['explanations_saved']}/12 |")
    intro+='\n'+'\n'.join(totals)+'\n'
    ordering=comp['ordering_probe']
    intro+=f"\n## Targeted Unicode-ordering probe\n\nA later source review, after {ordering['designed_after_completed_scored_attempts']} primary attempts had completed, found that Python code-point sorting can differ from JavaScript UTF-16 code-unit sorting. We froze four files with emoji and halfwidth katakana names, crossing versions and reverse flags. All four expected orders were checked against the original reader before testing any saved program. Every one of the nine tree attempts is included; no agent was restarted or decoder repaired. This source-driven post-hoc probe is separate from both earlier suites. Its inputs and expected answers are staged separately from the Python-only decoder execution.\n\n| Arm | Saved tree programs | Pass all four ordering checks |\n|---|---:|---:|\n"
    for arm,v in ordering['arms'].items():intro+=f"| {arm} | {v['submissions']}/3 | {v['passes']}/3 |\n"
    coverage=['| Arm | Complete token totals | Requests with unknown usage |','|---|---:|---:|']
    for arm in ('baseline','rea','data_only'):
        values=[m for m in comp['measurements'] if m['arm']==arm]
        coverage.append(f"| {arm} | {sum(m['token_total_available'] for m in values)} / 12 | {sum(m['unknown_usage_requests'] for m in values)} |")
    intro+='\nToken bars sum reported input and output tokens, including repeated context and schemas. Missing requests contribute unknown usage, not zero; these bars are lower bounds when coverage is incomplete. Cost reservations for those requests remain charged.\n\n'+'\n'.join(coverage)+'\n'
    exported=sum(m['arm']=='rea' and m['evidence_export_status']=='complete' for m in comp['measurements'])
    intro+=f'\nCanonical Evidence export completed for {exported} / 12 scored REA attempts. Export state is retained separately from functional scores.\n'
    intro+='\nThe evidence-integrity record preserves each analysis\'s application and semantic coverage separately. A complete retained application graph does not establish complete semantics or runtime reachability; unresolved relationships and provider limitations remain in the canonical bundles.\n'
    panels=[wr.BarPlot(title='Recorded / judged / behavior passes — twelve per arm',metrics=['recorded_attempt','checks_available','behavior_pass'],groupby=wr.Config('arm'),groupby_aggfunc='sum',groupby_rangefunc='none',range_x=(0,12),layout=wr.Layout(x=0,y=0,w=24,h=8)),
        wr.BarPlot(title='Hidden valid inputs passed — twelve per attempt',metrics=['valid_passed'],max_runs_to_show=36,max_bars_to_show=36,range_x=(0,12),layout=wr.Layout(x=0,y=8,w=24,h=15)),
        wr.BarPlot(title='Post-hoc audit: added valid inputs passed — sixteen per saved decoder',metrics=['stress_valid_passed'],max_runs_to_show=36,max_bars_to_show=36,range_x=(0,16),layout=wr.Layout(x=0,y=23,w=24,h=15)),
        wr.BarPlot(title='Reported task tokens — lower bound where usage is missing',metrics=['reported_tokens_lower_bound'],groupby=wr.Config('arm'),groupby_aggfunc='sum',groupby_rangefunc='none',range_x=(0,max(sum(m['reported_tokens_lower_bound'] for m in comp['measurements'] if m['arm']==arm) for arm in ('baseline','rea','data_only'))*1.05),layout=wr.Layout(x=0,y=38,w=24,h=8)),
        wr.BarPlot(title='Elapsed agent seconds per attempt',metrics=['agent_seconds'],max_runs_to_show=36,max_bars_to_show=36,layout=wr.Layout(x=0,y=46,w=24,h=15))]
    report=wr.Report(entity='wandb',project='rea-showcase',title='Standalone format recovery — ordinary tools, REA, and sample-only control',width='fluid',blocks=[wr.MarkdownBlock(text=intro),wr.PanelGrid(runsets=[wr.Runset(entity='wandb',project='rea-showcase',name='36 scored recoveries',filters=[expr.Config('experiment_id')==eid,expr.Config('phase')=='scored'])],panels=panels),wr.H2(text='Every attempt'),wr.MarkdownBlock(text='\n'.join(nav)),wr.H2(text='Evidence and limits'),wr.MarkdownBlock(text=f"[Immutable evidence artifact]({progress['artifact_url']}): `{progress['artifact']}`. All {len(manifest)} payload hashes matched downloaded files. Includes every input, original fixture source, independent reference checks, submitted decoders, case judgments, canonical Evidence and Agent Lens readbacks. These are small minified laboratory applications, not native-binary or large commercial-application results. Existing Piskel and dependency studies remain unchanged.")])
    report.save();progress['report_api_url']=report.url;write(root/'publication-progress.json',progress)
    observed=wr.Report.from_url(report.url);assert observed.title==report.title and len(observed.blocks)==6
    write(root/'report-readback.json',observed._to_model().model_dump(mode='json',by_alias=True,exclude_none=True))
    progress.update(state='saved_and_api_verified',report_url=forge_url(report.url,'wandb','rea-showcase'));write(root/'publication.json',progress)
    return progress

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--derive-only',action='store_true');a=p.parse_args()
    result=derive(a.root.resolve()) if a.derive_only else publish(a.root.resolve());print(json.dumps(result if not a.derive_only else result['arms'],indent=2))
