"""Draw the observed trigger distinction and export the complete eight-review table."""
from pathlib import Path
import argparse,csv,hashlib,json,statistics
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('article',type=Path);a=p.parse_args();r=a.root;out=a.article
s=json.loads((r/'summary.json').read_text());oracle=json.loads((r/'oracle.json').read_text())
assert len(s['attempts'])==8
left=r/'prepared/inputs/canary_hook/candidate/collect.js';right=r/'prepared/inputs/unreachable_helper/candidate/collect.js'
assert left.read_bytes()==right.read_bytes()
assert oracle['canary_hook']['candidate']['install']['records_canary']
assert not any(oracle['unreachable_helper']['candidate'][k]['records_canary'] for k in ('install','import_default','import_opt_in'))
plt.rcParams.update({'font.family':'DejaVu Sans','text.color':'#20303c','figure.facecolor':'#fbfbf8'})
fig,ax=plt.subplots(figsize=(11,5.5));ax.set_xlim(0,11);ax.set_ylim(0,5.5);ax.axis('off')
def box(x,y,w,h,title,body,color='#e6eeef'):
 ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.12',facecolor=color,edgecolor='#8ca1a7',linewidth=1))
 ax.text(x+.13,y+h-.27,title,fontsize=12,weight='bold',va='top')
 ax.text(x+.13,y+h-.69,body,fontsize=10.5,va='top',linespacing=1.5)
def arrow(x1,y1,x2,y2):ax.annotate('',xy=(x2,y2),xytext=(x1,y1),arrowprops={'arrowstyle':'->','color':'#2e6970','lw':2})
ax.text(0,5.35,'The same helper can run—or merely be shipped',fontsize=21,weight='bold')
ax.text(0,4.95,'Original laboratory fixtures · observed with a dummy token and a local recorder',fontsize=11,color='#526672')
ax.text(0,4.5,'INSTALL-HOOK CASE',fontsize=11,weight='bold')
box(.1,2.9,2.6,1.3,'Declared postinstall','node install.js')
box(3.2,2.9,2.6,1.3,'Called helper','collect() reads\nbuild-token.txt')
box(6.3,2.9,2.6,1.3,'Local recorder','Appends the dummy value\nto a local JSONL file')
arrow(2.85,3.55,3.05,3.55);arrow(5.95,3.55,6.15,3.55)
ax.text(9.25,3.75,'OBSERVED',fontsize=10,weight='bold');ax.text(9.25,3.36,'Read + record',fontsize=11,color='#176050');ax.text(9.25,3.02,'No network sink',fontsize=9.5)
ax.text(0,2.35,'UNUSED-HELPER CONTROL',fontsize=11,weight='bold')
box(.1,.7,2.6,1.3,'Default entry','Exports a color() function')
box(3.2,.7,2.6,1.3,'Same helper file','Present, but not imported\nor called by the entry',color='#f0eeea')
ax.text(6.25,1.65,'No install hook.\nFlag adds no call.',fontsize=11,linespacing=1.7)
ax.text(9.25,1.65,'OBSERVED',fontsize=10,weight='bold');ax.text(9.25,1.26,'No token read',fontsize=10.5);ax.text(9.25,.92,'No local record',fontsize=10.5)
ax.text(0,.1,'Conclusion is limited to the declared install/import scenarios. Explicit calls to the helper are outside this test.',fontsize=10,color='#526672')
fig.savefig(out/'assets/dependency-triggers.png',dpi=160,bbox_inches='tight');fig.savefig(out/'assets/dependency-triggers.svg',bbox_inches='tight');plt.close(fig)
rows=[]
for v in s['attempts']:
 u=v['usage'];events=json.loads((r/'attempts'/v['attempt_id']/'events.json').read_text())
 rows.append({'attempt_id':v['attempt_id'],'fixture':v['fixture'],'arm':v['arm'],'facts_correct':v.get('checker',{}).get('facts_correct'),'facts_total':9,'passed':v.get('checker',{}).get('passed'),'tokens':u['input_tokens']+u['output_tokens'] if not u['unknown_usage_requests'] else None,'elapsed_seconds':v['agent_elapsed_seconds'],'conservative_cost_estimate_usd':u['reserved_or_estimated_usd'],'rea_calls':sum(e['kind']=='tool' and e['tool'] not in ('list_files','read_file','search') for e in events),'tool_errors':sum(bool(e.get('error')) for e in events)})
arms={}
for arm in ('baseline','rea'):
 group=[v for v in rows if v['arm']==arm]
 arms[arm]={'attempts':len(group),'passes':sum(v['passed'] for v in group),'facts_correct':sum(v['facts_correct'] for v in group),'facts_total':9*len(group),'median_task_tokens':statistics.median(v['tokens'] for v in group),'median_seconds':statistics.median(v['elapsed_seconds'] for v in group),'total_task_tokens':sum(v['tokens'] for v in group),'cost_estimate_usd':sum(v['conservative_cost_estimate_usd'] for v in group)}
with (out/'data/dependency-reviews.csv').open('w') as f:
 writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
(out/'data/dependency-results.json').write_text(json.dumps({'experiment_id':s['experiment_id'],'source_summary_sha256':hashlib.sha256((r/'summary.json').read_bytes()).hexdigest(),'oracle_sha256':hashlib.sha256((r/'oracle.json').read_bytes()).hexdigest(),'same_helper_sha256':hashlib.sha256(left.read_bytes()).hexdigest(),'arms':arms,'rows':rows,'source_scope':'Four original synthetic release pairs, one review per arm per pair; separate from animation study.'},indent=2)+'\n')
print(json.dumps(arms,indent=2))
