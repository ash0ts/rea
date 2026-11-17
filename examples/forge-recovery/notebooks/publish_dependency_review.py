"""Publish only recorded dependency-review evidence; no model or target execution."""
from __future__ import annotations
import argparse, hashlib, json, netrc, os
from collections import defaultdict, deque
from pathlib import Path
import wandb
from publish_dashboard import forge_url
from verify_trace_joins import recorded_value


def read(p):return json.loads(p.read_text())
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def verify_attempt(folder):
    r=read(folder/'result.json');events=read(folder/'events.json');messages=read(folder/'messages.json');spans=read(folder/'lens-readback.json')['spans']
    assert r['cleanup_status']=='complete' and r['lens_status']=='verified'
    by={(s['trace_id'],s['span_id']):s for s in spans};assert len(by)==len(spans)
    roots={k for k,s in by.items() if s['operation_name']=='invoke_agent'};assert len(roots)==1
    tools=[e for e in events if e['kind']=='tool'];pending=defaultdict(deque);i=0
    for s in spans:
        if s['operation_name'] in ('chat','execute_tool'):assert (s['trace_id'],s['parent_span_id']) in roots and s['conversation_id']==r['attempt_id']
    for m in messages:
        if m['role']=='assistant':
            for c in m.get('tool_calls',[]):pending[c['id']].append(c)
        elif m['role']=='tool':
            c=pending[m['tool_call_id']].popleft();e=tools[i];s=by[e['trace_id'],e['span_id']]
            assert s['tool_call_id']==c['id']==m['tool_call_id']==e['tool_call_id']
            assert s['tool_name']==e['tool']==c['function']['name']
            assert recorded_value(s['tool_call_arguments'])==recorded_value(c['function']['arguments'])
            assert recorded_value(s['tool_call_result'])==recorded_value(m['content'])
            i+=1
    assert i==len(tools)
    models=[s for s in spans if s['operation_name']=='chat'];assert len(models)==r['usage']['requests']
    return {'attempt_id':r['attempt_id'],'model_spans':len(models),'tool_argument_response_pairs':i,'tool_errors':sum(s['operation_name']=='execute_tool' and s['status_code']=='ERROR' for s in spans),'pending_tool_responses':sum(len(v) for v in pending.values()),'source_sha256':{n:sha(folder/n) for n in ('result.json','events.json','messages.json','lens-readback.json')}}


def publish(root):
    import wandb_workspaces.reports.v2 as wr
    from wandb_workspaces import expr
    if (root/'publication.json').exists():return read(root/'publication.json')
    if (root/'publication-progress.json').exists():raise RuntimeError('Publication may exist; inspect saved identities before retry')
    conf=read(root/'experiment.json');summary=read(root/'summary.json');rows=summary['attempts'];eid=conf['experiment_id']
    assert len(rows)==8 and {r['attempt_id'] for r in rows}=={r['attempt_id'] for r in conf['attempts']}
    audit=[verify_attempt(root/'attempts'/s['attempt_id']) for s in conf['qualification']+conf['attempts']]
    write(root/'lens-integrity.json',{'attempts':audit,'scope':'Stored span identity, parentage, arguments and delivered results; semantic support is audited separately.'})
    assert all(r['cleanup_status']=='complete' and r['upload_status']=='complete' for r in rows)
    os.environ.setdefault('WANDB_API_KEY',netrc.netrc().authenticators('api.wandb.ai')[2])
    api=wandb.Api(timeout=60)
    project=api._service_api.execute_graphql('query{project(name:"rea-showcase",entityName:"wandb"){access}}',{})['project']
    assert project['access'].upper()=='PRIVATE'
    progress={'experiment_id':eid,'state':'publishing'};write(root/'publication-progress.json',progress)
    measurements=[]
    for r in rows:
        events=read(root/'attempts'/r['attempt_id']/'events.json');u=r['usage'];c=r.get('checker',{});resources=r.get('agent_resources',{})
        m={'recorded_review':1,'review_checks_available':int('passed' in c),'review_pass':int(c['passed']) if 'passed' in c else None,'review_facts_correct':c.get('facts_correct'),'task_tokens':u['input_tokens']+u['output_tokens'] if u['unknown_usage_requests']==0 else None,'agent_seconds':r['agent_elapsed_seconds'],'conservative_cost_estimate_usd':u['reserved_or_estimated_usd'],'current_rate_estimate_usd':(u['input_tokens']*.60+u['output_tokens']*3.0)/1e6 if u['unknown_usage_requests']==0 else None,'rea_calls':sum(e['kind']=='tool' and e['tool'] not in ('list_files','read_file','search') for e in events),'container_cpu_seconds':resources.get('container_cpu_seconds'),'container_peak_memory_bytes':resources.get('container_peak_memory_bytes'),'agent_lens_url':r['lens_url'],'source_artifact':r['publication']['artifact']}
        run=api.run('wandb/rea-showcase/'+r['attempt_id']);run.summary.update(m)
        observed=dict(api.run('wandb/rea-showcase/'+r['attempt_id']).summary)
        assert all(observed.get(k)==v for k,v in m.items()),r['attempt_id']
        measurements.append({'attempt_id':r['attempt_id'],'fixture':r['fixture'],'arm':r['arm'],**m})
    write(root/'measurements.json',measurements)
    files={}
    def add(path,name):files[name]=path
    for n in ('experiment.json','oracle.json','summary.json','budget.json','qualification.json','measurements.json','lens-integrity.json','live-sandbox-safety.json','semantic-audit.json'):
        add(root/n,n)
    for p in (root/'prepared').rglob('*'):
        if p.is_file():add(p,str(p.relative_to(root)))
    for p in (root/'oracle-runs').rglob('observed.json'):add(p,str(p.relative_to(root)))
    for p in root.rglob('*.container.json'):add(p,str(p.relative_to(root)))
    for s in conf['qualification']+conf['attempts']:
        folder=root/'attempts'/s['attempt_id']
        for n in ('result.json','review.json','events.json','messages.json','lens-readback.json'):
            if (folder/n).exists():add(folder/n,str((folder/n).relative_to(root)))
        for sub in ('evidence','checks','work/tool-results'):
            for p in (folder/sub).rglob('*'):
                if p.is_file():add(p,str(p.relative_to(root)))
    example=Path(__file__).resolve().parents[1]
    for rel,digest in conf['code'].items():
        p=example/rel;assert sha(p)==digest,'Frozen source changed: '+rel
        add(p,'source/'+rel)
    for name in ('dependency_review/RESEARCH.md','notebooks/publish_dependency_review.py'):
        add(example/name,'source/'+name)
    manifest={n:sha(p) for n,p in files.items()};write(root/'evidence-manifest.json',manifest);add(root/'evidence-manifest.json','evidence-manifest.json')
    with wandb.init(entity='wandb',project='rea-showcase',id=eid+'-evidence',job_type='dependency-review-evidence',dir=str(root),settings=wandb.Settings(disable_git=True,disable_code=True,console='off')) as run:
        artifact=wandb.Artifact(eid+'-evidence',type='dependency-review-evidence',metadata={'configuration_sha256':conf['configuration_sha256'],'scored_attempts':8,'qualification_attempts':2})
        for name,path in files.items():artifact.add_file(str(path),name=name)
        a=run.log_artifact(artifact).wait();progress.update(artifact=f'wandb/rea-showcase/{a.name}',artifact_digest=a.digest)
        write(root/'publication-progress.json',progress)
    downloaded=Path(api.artifact(progress['artifact']).download(root=str(root/'artifact-readback')))
    assert all(sha(downloaded/n)==digest for n,digest in manifest.items())
    assert sha(downloaded/'evidence-manifest.json')==sha(root/'evidence-manifest.json')
    progress['verified_artifact_files']=len(manifest);write(root/'publication-progress.json',progress)
    nav=['| Release pair | Arm | Correct facts / 9 | Result | Evidence |','|---|---|---:|---|---|']
    for r in rows:
        c=r.get('checker',{});nav.append(f"| {r['fixture']} | {r['arm']} | {c.get('facts_correct','Unavailable')} | {r['task_status']} | [Agent Lens]({r['lens_url']}) · [Run / files]({r['publication']['run_url']}) |")
    intro='''## Four release pairs, eight static reviews

Original laboratory packages, not real malware. Independent isolated executions observed dummy-token reads, local recording, and generated assets under three explicit install/import scenarios. Both arms use Kimi-K2.7-Code and read-only source tools; the REA-assisted arm is guided to analyze both directories and compare versions. Nine Boolean facts per attempt plus exact source quotations are graded. Narrative support is reviewed separately.

One attempt per arm per pair; no statistical superiority claim. Qualification is separate. No target execution is exposed to agents. Containers have no network or model credentials. Unknowns and failed calls remain in the traces. Tokens include repeated context and schemas; costs are estimates, not billing. Local CPU/memory exclude remote inference.
'''
    filters=[expr.Config('experiment_id')==eid,expr.Config('phase')=='scored']
    panels=[wr.BarPlot(title='Recorded / judged / passing reviews — four per arm',metrics=['recorded_review','review_checks_available','review_pass'],groupby=wr.Config('arm'),groupby_aggfunc='sum',groupby_rangefunc='none',range_x=(0,4),layout=wr.Layout(x=0,y=0,w=24,h=8)),wr.BarPlot(title='Correct scenario facts — nine per review',metrics=['review_facts_correct'],range_x=(0,9),max_runs_to_show=8,max_bars_to_show=8,layout=wr.Layout(x=0,y=8,w=24,h=10)),wr.BarPlot(title='Task tokens, including schemas and repeated context',metrics=['task_tokens'],max_runs_to_show=8,max_bars_to_show=8,layout=wr.Layout(x=0,y=18,w=24,h=10)),wr.BarPlot(title='Elapsed agent seconds',metrics=['agent_seconds'],max_runs_to_show=8,max_bars_to_show=8,layout=wr.Layout(x=0,y=28,w=24,h=10))]
    report=wr.Report(entity='wandb',project='rea-showcase',title='Dependency review — contained release-pair experiment',width='fluid',blocks=[wr.MarkdownBlock(text=intro),wr.PanelGrid(runsets=[wr.Runset(entity='wandb',project='rea-showcase',name='Eight scored reviews',filters=filters)],panels=panels),wr.H2(text='Every scored review'),wr.MarkdownBlock(text='\n'.join(nav)),wr.H2(text='Reproduce and inspect'),wr.MarkdownBlock(text=f"Immutable evidence: `{progress['artifact']}`. All {len(manifest)} file hashes matched downloaded bytes. The package contains fixtures, runtime receipts, source, submissions, canonical REA Evidence, checks and Agent Lens readbacks. The original animation campaign is unchanged.")])
    report.save();progress['report_api_url']=report.url;write(root/'publication-progress.json',progress)
    observed=wr.Report.from_url(report.url);assert observed.title==report.title and len(observed.blocks)==6
    ids={r.id for r in api.runs('wandb/rea-showcase',filters={'config.experiment_id':eid,'config.phase':'scored'})};assert ids=={r['attempt_id'] for r in rows}
    write(root/'report-readback.json',observed._to_model().model_dump(mode='json',by_alias=True,exclude_none=True))
    progress.update(state='saved_and_api_verified',report_url=forge_url(report.url,'wandb','rea-showcase'),scored_attempts=8,qualification_attempts=2)
    write(root/'publication.json',progress);return progress

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);args=p.parse_args();print(json.dumps(publish(args.root.resolve()),indent=2))
