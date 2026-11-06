"""Generate review figures from retained records. Never execute submitted code."""
from pathlib import Path
import argparse, base64, csv, hashlib, io, json, os
os.environ.setdefault('MPLCONFIGDIR', '/tmp/rea-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch
import numpy as np
from PIL import Image, ImageDraw

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root',type=Path,required=True,help='Retained .local directory, or extracted raw/ evidence directory')
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
ROOT=args.root.resolve()
OUT=args.output.resolve(); OUT.mkdir(parents=True,exist_ok=True)
ASSETS=OUT/'figures'; ASSETS.mkdir(exist_ok=True)
DATA=OUT/'data'; DATA.mkdir(exist_ok=True)
sources={}
def record(p):
    p=Path(p); sources[str(p.relative_to(ROOT))]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}; return p
def read(p): return json.loads(record(p).read_text())
def load_png(p): return Image.open(record(p)).convert('RGBA')
def save_json(p,x): p.write_text(json.dumps(x,indent=2)+'\n')
experiment=read(ROOT/'experiment-v5/experiment.json')
specs=experiment['attempts']; rows=[]; by_id={}; full=[]
for spec in specs:
    path=ROOT/'experiment-v5/attempts'/spec['attempt_id']/'result.json'
    result=read(path) if path.exists() else None
    row={**spec,'recorded':result is not None,'task_status':result['task_status'] if result else 'not_run',
         'checker_passed':(result.get('checker') or {}).get('passed') if result else None}
    if result:
        full.append(result)
        usage=result.get('usage') or {}
        row.update(requests=usage.get('requests'),tokens=usage.get('input_tokens',0)+usage.get('output_tokens',0) if usage and usage.get('unknown_usage_requests')==0 else None,
            agent_seconds=result.get('agent_elapsed_seconds'),estimated_usd=usage.get('reserved_or_estimated_usd'),
            cpu_seconds=(result.get('agent_resources') or {}).get('container_cpu_seconds'),
            peak_memory_bytes=(result.get('agent_resources') or {}).get('container_peak_memory_bytes'))
        events=read(path.parent/'events.json')
        row['rea_calls']=sum(e.get('kind')=='tool' and e.get('tool')!='execute' for e in events)
        row['checker']=result.get('checker')
    rows.append(row); by_id[spec['attempt_id']]=row
assert len(rows)==24 and len(full)==4
dataset={'recorded':4,'planned':24,'score_basis':'Original checks; all preview judgments provisional',
    'claims':'One fixture family observed; no completed REA effect estimate','attempts':rows}
save_json(DATA/'recorded-comparison.json',dataset)
columns=['fixture','arm','repetition','recorded','task_status','checker_passed','requests','tokens','agent_seconds','estimated_usd','cpu_seconds','peak_memory_bytes','rea_calls']
with (DATA/'attempts.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(rows)

INK='#202c3b'; MUTED='#536477'; BASE='#287ca4'; REA='#c06c28'; PASS='#24786a'; FAIL='#bd4f43'; MISSING='#e2e7ec'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12,'text.color':INK,'axes.labelcolor':INK,'xtick.color':MUTED,'ytick.color':INK,'axes.spines.top':False,'axes.spines.right':False,'axes.spines.left':False,'axes.spines.bottom':False,'figure.facecolor':'#fafbf9','axes.facecolor':'#fafbf9','svg.fonttype':'none'})
figures=[]
def finish(fig,name,title,caption,kind='measurement'):
    fig.savefig(ASSETS/f'{name}.png',dpi=150,bbox_inches='tight',facecolor=fig.get_facecolor())
    fig.savefig(ASSETS/f'{name}.svg',bbox_inches='tight',facecolor=fig.get_facecolor())
    figures.append({'file':name+'.png','title':title,'caption':caption,'class':kind})
    plt.close(fig)
def backed(im):
    a=np.array(im); h,w=a.shape[:2]; yy,xx=np.indices((h,w)); gray=np.where((xx//3+yy//3)%2,222,250)
    bg=np.stack([gray,gray,gray,np.full_like(gray,255)],axis=-1).astype('uint8')
    return np.array(Image.alpha_composite(Image.fromarray(bg),im))
def sprite(ax,im): ax.imshow(backed(im),interpolation='nearest'); ax.set_xticks([]);ax.set_yticks([])

families=['basic','opacity','non_square','chunks','hidden','legacy']
names={'basic':'Basic animation','opacity':'Translucent layers','non_square':'Non-square frames','chunks':'Multiple image chunks','hidden':'Hidden frames','legacy':'Legacy storage'}
fig,axes=plt.subplots(3,2,figsize=(10,5.8),layout='constrained')
for ax,family in zip(axes.flat,families):
    p=ROOT/'prepared-v2/oracle'/family/'visible'; expected=read(p/'expected.json')
    frames=[load_png(p/f'frame-{i:03}.png') for i in range(expected['frame_count'])]
    width=sum(im.width for im in frames)+3*(len(frames)-1); strip=Image.new('RGBA',(width,max(im.height for im in frames)))
    x=0
    for im in frames:strip.paste(im,(x,0));x+=im.width+3
    sprite(ax,strip)
    ax.set_title(names[family],loc='left',fontweight='bold',pad=16)
    detail=f"{expected['width']} × {expected['height']} px · {len(frames)} frames · {expected['fps']} FPS"
    if family=='opacity':detail+='\nLayer opacity: 1, 0.5, 0.75'
    if family=='hidden':detail+='\nFrames 2 and 5 exported; omitted in playback'
    if family=='chunks':detail+='\nFile chunk order: [5,6], [3,4], [1,2]'
    ax.set_xlabel(detail,labelpad=14,fontsize=11)
fig.suptitle('Six inputs that expose different decoding mistakes',x=.02,ha='left',fontsize=19,fontweight='bold')
finish(fig,'fixture-atlas','Six fixture families','Original Piskel renderings of visible fixtures. Only the basic family has scored records so far; these are not six recovered successes.','reference outputs')

p=ROOT/'prepared-v2/oracle/chunks/visible'; doc=read(p/'animation.piskel'); layer=json.loads(doc['piskel']['layers'][0])
fig,axes=plt.subplots(2,3,figsize=(9.5,5.1),layout='constrained')
for j,chunk in enumerate(layer['chunks']):
    im=Image.open(io.BytesIO(base64.b64decode(chunk['base64PNG'].split(',',1)[1]))).convert('RGBA')
    sprite(axes[0,j],im); ids=[i+1 for col in chunk['layout'] for i in col]
    axes[0,j].set_title(f'File chunk {j+1}\nlayout → frames {ids[0]}, {ids[1]}',fontsize=12)
for j in range(3):
    strip=Image.new('RGBA',(48,24))
    for k in range(2):strip.paste(load_png(p/f'frame-{2*j+k:03}.png'),(24*k,0))
    sprite(axes[1,j],strip);axes[1,j].set_title(f'Playback positions {2*j+1}, {2*j+2}',fontsize=12)
fig.suptitle('Read the chunk layout before choosing frame order',x=.02,ha='left',fontsize=18,fontweight='bold')
finish(fig,'chunk-layout','Chunk order differs from playback order','The saved file stores chunks in reverse sequence. Layout indexes recover the correct six-frame ordering. Frame labels here are one-based.','format explanation')

p=ROOT/'prepared-v2/oracle/opacity/visible'; expected=read(p/'expected.json')
fig,axes=plt.subplots(1,4,figsize=(9,3.4),layout='constrained')
for i in range(3):
    sprite(axes[i],load_png(p/f'layer-{i}-003.png')); axes[i].set_title(f'Layer {i+1}\nopacity {expected["layer_opacities"][i]}',fontsize=12)
sprite(axes[3],load_png(p/'frame-003.png'));axes[3].set_title('Piskel composite\nframe 4',fontsize=12,fontweight='bold')
fig.suptitle('Correct crops still need the right layer composition',fontsize=18,fontweight='bold')
finish(fig,'opacity-layers','Layers and original composite','Stored layer pixels and original application composite for the opacity fixture. The opacity family has not yet been scored.','reference outputs')

p=ROOT/'experiment-v5/attempts/recovery-aa7c373605fd-basic-rea-1/checks/heldout/verified-output'; man=read(p/'manifest.json')
audit=[]; fig,axes=plt.subplots(3,3,figsize=(9,5.8),layout='constrained'); moving=[]
for i,ax in enumerate(axes.flat):
    ref=load_png(ROOT/f'prepared-v2/oracle/basic/heldout/frame-{i:03}.png'); rec=load_png(p/man['frames'][i])
    a,b=np.asarray(ref).astype('int16'),np.asarray(rec).astype('int16'); diff=np.any(a!=b,axis=2)
    n=int(diff.sum()); assert ref.size==rec.size and n==0
    audit.append({'frame_index':i,'rgba_different_pixels':n,'dimensions':list(ref.size)})
    strip=np.concatenate([backed(ref),np.full((24,3,4),255,dtype='uint8'),backed(rec),np.full((24,3,4),255,dtype='uint8'),np.dstack([np.where(diff,190,235),np.where(diff,40,239),np.where(diff,40,241),np.full((24,24),255)]).astype('uint8')],axis=1)
    ax.imshow(strip,interpolation='nearest');ax.set_xticks([12,39,66],['Original','Recovered','Δ RGBA'],fontsize=9);ax.set_yticks([]);ax.set_title(f'Frame {i+1} · 0 different pixels',fontsize=11)
    moving.append(Image.fromarray(np.concatenate([backed(ref),np.full((24,4,4),255,dtype='uint8'),backed(rec)],axis=1)).resize((520,240),Image.Resampling.NEAREST))
fig.suptitle('Every unseen frame matches, including alpha',fontsize=19,fontweight='bold')
finish(fig,'pixel-audit','Nine-frame RGBA audit','All nine retained unseen frames match in width, height and every RGBA channel. Light-gray difference panes mean zero differing pixels. Playback timing is a separate check.')
save_json(DATA/'pixel-audit.json',audit)
moving[0].save(ASSETS/'recovered-animation.png',save_all=True,append_images=moving[1:],duration=1000/13,loop=0,disposal=0,blend=0)
figures.append({'file':'recovered-animation.png','title':'Original and recovered frames in motion','class':'recorded-frame animation','caption':'Left: Piskel reference. Right: recovered output. Animation assembled from the retained nine PNGs at approximately 13 FPS for inspection; this is not a browser-timing measurement.'})

fig,ax=plt.subplots(figsize=(8,6.3)); fig.subplots_adjust(left=.25,right=.98,top=.82,bottom=.20)
conditions=[('baseline',1),('rea',1),('baseline',2),('rea',2)]
colors={'pass':PASS,'fail':FAIL,'unavailable':MISSING,'not_run':'#f8f9fa'}
for y,family in enumerate(families):
    for x,(arm,rep) in enumerate(conditions):
        r=next(r for r in rows if r['fixture']==family and r['arm']==arm and r['repetition']==rep)
        status='not_run' if not r['recorded'] else 'pass' if r['checker_passed'] is True else 'fail' if r['checker_passed'] is False else 'unavailable'
        ax.add_patch(Rectangle((x-.45,y-.4),.9,.8,facecolor=colors[status],edgecolor='#c7cfd8',hatch='///' if status=='not_run' else None,lw=.8))
        text={'pass':'Pass*','fail':'Fail*','unavailable':'No check','not_run':'Not run'}[status]
        ax.text(x,y,text,ha='center',va='center',color='white' if status in ['pass','fail'] else INK,fontsize=11)
ax.set_xlim(-.5,3.5);ax.set_ylim(5.5,-.6);ax.set_yticks(range(6),[names[x] for x in families]);ax.set_xticks(range(4),['Baseline\nrep. 1','REA\nrep. 1','Baseline\nrep. 2','REA\nrep. 2']);ax.tick_params(length=0,pad=10)
fig.suptitle('Four recorded attempts; twenty still unrun',fontsize=18,fontweight='bold',x=.03,ha='left')
fig.text(.03,.035,'*Original overall judgment. Preview checks remain provisional.\nAll four records come from the basic family. Not run ≠ failed.',fontsize=11)
finish(fig,'attempt-coverage','24 planned slots, four records','Original checks shown with explicit missingness. REA repetition 2 failed unseen preview timing under the defective original clock; its pixel checks passed.')

criteria=[('pixels','Pixels'),('frame_order','Order'),('dimensions','Size'),('fps','FPS'),('hidden_frames','Hidden'),('sprite_sheet','Sheet'),('preview_playback','Play*'),('preview_scrubbing','Scrub*'),('preview_download','Export*')]
crit_rows=[]
for r in rows[:4]:
    for case in ['visible','heldout']:
        c=(r.get('checker') or {}).get('cases',{}).get(case,{})
        vals=[]
        for key,label in criteria:
            v=c.get('preview',{}).get(key.removeprefix('preview_')) if key.startswith('preview_') else c.get('pixels',{}).get('criteria',{}).get(key)
            vals.append(v)
            crit_rows.append({'arm':r['arm'],'repetition':r['repetition'],'case':case,'criterion':key,'value':v})
fig,ax=plt.subplots(figsize=(10,5.6));fig.subplots_adjust(left=.29,right=.98,top=.82,bottom=.23)
for y in range(8):
    rowcrit=crit_rows[y*9:(y+1)*9]
    for x,c in enumerate(rowcrit):
        v=c['value'];ax.add_patch(Rectangle((x-.46,y-.4),.92,.8,facecolor=PASS if v is True else FAIL if v is False else MISSING,edgecolor='white'))
        ax.text(x,y,'✓' if v is True else '×' if v is False else '—',ha='center',va='center',color='white' if v is not None else MUTED,fontsize=13)
labels=[f"{r['arm'].upper()} {r['repetition']} · {case}" for r in rows[:4] for case in ['visible','unseen']]
ax.set_xlim(-.5,8.5);ax.set_ylim(7.5,-.5);ax.set_xticks(range(9),[s[1] for s in criteria]);ax.set_yticks(range(8),labels);ax.tick_params(length=0,pad=8)
fig.suptitle('Separate recovered pixels from browser behavior',x=.02,ha='left',fontsize=18,fontweight='bold')
fig.text(.02,.04,'✓ Pass   × Fail   — Criterion unavailable\n*Original browser checks, provisional. Missing decoder and unavailable checker stay distinct in the attempt record.',fontsize=10)
finish(fig,'criterion-matrix','Criterion-level checks','Both treatment submissions pass pixel and metadata checks. The original timing failure is separate; baseline repetition 1 records failed pixel criteria because no decoder was submitted; baseline repetition 2 has no judgment.')
with (DATA/'criteria.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=list(crit_rows[0]));w.writeheader();w.writerows(crit_rows)

fig,axes=plt.subplots(3,1,figsize=(9,9),layout='constrained')
for ax,key,title,scale,fmt in zip(axes,['tokens','agent_seconds','estimated_usd'],['Total task tokens (millions)','Agent elapsed seconds, including finalization','Uncached-rate cost estimate / reservation (USD)'],[1e6,1,1],['.3f','.1f','.3f']):
    for y,r in enumerate(rows[:4]):
        val=r[key]/scale;ax.barh(y,val,color=BASE if r['arm']=='baseline' else REA,height=.58)
        ax.text(val,y,' '+format(val,fmt),va='center',fontsize=11)
    ax.set_yticks(range(4),[f"{r['arm'].upper()} · rep {r['repetition']}" for r in rows[:4]]);ax.invert_yaxis();ax.set_title(title,loc='left',fontsize=13,fontweight='bold');ax.set_xlim(0,max(r[key]/scale for r in rows[:4])*1.20);ax.grid(axis='x',alpha=.17);ax.set_axisbelow(True)
fig.suptitle('Retain the cost of failed and interrupted work',fontsize=19,fontweight='bold')
finish(fig,'attempt-resources','Resource use for all recorded attempts','Token totals include schemas and repeated context. Baseline repetition 2 timed out during the VM incident. These are four attempts with different outcomes, not an efficiency ranking; cost is not settled billing.')

fig,axes=plt.subplots(2,1,figsize=(9,6.5),layout='constrained')
for ax,key,title,scale in zip(axes,['cpu_seconds','peak_memory_bytes'],['Agent container CPU seconds','Peak agent process-family memory (MiB)'],[1,1048576]):
    available=[r[key]/scale for r in rows[:4] if r.get(key) is not None]
    for y,r in enumerate(rows[:4]):
        if r.get(key) is None:
            ax.text(0,y,'Unavailable after VM failure',va='center',color=MUTED,fontsize=11)
        else:
            value=r[key]/scale;ax.barh(y,value,color=BASE if r['arm']=='baseline' else REA,height=.58);ax.text(value,y,f' {value:.1f}',va='center',fontsize=11)
    ax.set_yticks(range(4),[f"{r['arm'].upper()} · rep {r['repetition']}" for r in rows[:4]]);ax.invert_yaxis();ax.set_title(title,loc='left',fontweight='bold',fontsize=13);ax.set_xlim(0,max(available)*1.25);ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
fig.suptitle('Local resource measurements have a clear boundary',fontsize=18,fontweight='bold')
finish(fig,'local-resources','CPU and memory with missingness','Measurements cover the agent container process family. Remote inference resources and per-attempt controller peak memory are not included. Missing VM accounting is unavailable, not zero.')

clock=read(ROOT/'experiment-v5/diagnostics/clock-validation.json')
fig,axes=plt.subplots(2,1,figsize=(8,7.4),layout='constrained')
clock_rows=[]
for ax,key,title in zip(axes,['original-clock','paused-clock'],['Original checker: uncounted time accumulates','Paused diagnostic: the two timelines agree']):
    t=clock['variants'][key]['parsed']['timing'];x=np.array(t['requested_changes']);y=np.array(t['clock_changes']);drift=y-x
    ax.plot(x,drift,'o-',color=FAIL if key=='original-clock' else PASS,ms=4)
    ax.axhline(0,color=MUTED,lw=.8);ax.set_xlim(0,2000);ax.set_ylim(-30,600);ax.set_ylabel('Browser − driver (ms)');ax.set_xlabel('Driver-accounted time (ms)');ax.grid(alpha=.15);ax.set_title(title,loc='left',fontsize=13)
    ax.annotate(f'{int(drift[-1])} ms drift\n{int(x[-1])} → {int(y[-1])} ms',(x[-1],drift[-1]),xytext=(-155,-20 if key=='original-clock' else 65),textcoords='offset points',fontsize=11,arrowprops={'arrowstyle':'-','color':MUTED})
    clock_rows.extend({'variant':key,'transition':i,'driver_ms':int(a),'browser_ms':int(b),'drift_ms':int(b-a)} for i,(a,b) in enumerate(zip(x,y)))
fig.suptitle('The checker’s clock changed the timing judgment',fontsize=18,fontweight='bold')
finish(fig,'clock-drift','Clock drift diagnostic','One retained unseen preview, two checker diagnostics. The paused diagnostic passes timing; it does not replace the campaign’s original scores or validate every corrected browser regression.')
save_json(DATA/'clock-transitions.json',clock_rows)

lens=read(ROOT/'experiment-v5/attempts/recovery-aa7c373605fd-basic-rea-2/lens-readback.json')
calls=sorted([s for s in lens['spans'] if s['tool_name']=='analyze_javascript_application'],key=lambda s:s['started_at'])
assert len(calls)==3
fig,ax=plt.subplots(figsize=(9,6.3));ax.axis('off');ax.set_xlim(0,10);ax.set_ylim(0,7)
labels=[('1','Invalid format argument','format="javascript" rejected by the input schema',FAIL),('2','Unsupported target','format="auto", but a raw .js file is not an application directory',FAIL),('3','Directory analysis succeeds','The agent stages a directory and receives an Evidence reference',PASS)]
for y,(num,title,detail,color) in zip([5.7,3.6,1.5],labels):
    ax.add_patch(Rectangle((.3,y-.55),.7,1.1,facecolor=color));ax.text(.65,y,num,ha='center',va='center',color='white',fontsize=20,fontweight='bold')
    ax.text(1.3,y+.23,title,fontsize=16,fontweight='bold');ax.text(1.3,y-.22,detail,fontsize=11)
    if num!='3':ax.add_patch(FancyArrowPatch((.65,y-.63),(.65,y-1.45),arrowstyle='->',mutation_scale=15,color=MUTED))
fig.suptitle('The treatment agent corrected two failed REA calls',fontsize=18,fontweight='bold',x=.05,ha='left')
finish(fig,'rea-tool-sequence','Actual REA call sequence','Treatment repetition 2: three returned analysis calls, two errors and one success. This is a reconstruction from stored spans, not a screenshot or a causal claim that the tool improved recovery.','trace reconstruction')
save_json(DATA/'rea-calls.json',[{k:s[k] for k in ['span_id','parent_span_id','tool_call_id','tool_name','status_code','started_at','ended_at','tool_call_arguments']} for s in calls])

fig,ax=plt.subplots(figsize=(8.5,8));ax.set_xlim(0,10);ax.set_ylim(0,10);ax.axis('off')
stages=[('Frozen task','Bundle + input + model settings','Agent receives only its staged inputs'),('Recorded attempt','Conversation + model/tool spans','Tool-call IDs connect each request and result'),('Retained submission','Decoder + exported REA Evidence','Evidence is exported before the MCP session closes'),('Independent check','Fresh input → new PNGs + browser checks','Original application renders the reference pixels'),('Review surfaces','Artifacts → dashboard + notebooks','Controls inspect stored work; no inference is launched')]
for i,(title,objects,meaning) in enumerate(stages):
    y=9-i*1.9
    ax.add_patch(Rectangle((.5,y-.63),9,1.35,facecolor='#edf2f5',edgecolor='#b9c8d4'))
    ax.text(.8,y+.34,title,fontweight='bold',fontsize=14);ax.text(.8,y-.02,objects,fontsize=12);ax.text(.8,y-.37,meaning,fontsize=10,color=MUTED)
    if i<4:ax.add_patch(FancyArrowPatch((5,y-.66),(5,y-1.13),arrowstyle='->',mutation_scale=16,color=INK))
fig.suptitle('Follow one attempt from its input to its pixels',fontsize=18,fontweight='bold')
finish(fig,'evidence-chain','Evidence ownership across the workflow','An implementation diagram. The attempt identity joins each retained stage; a saved view does not establish that its output is correct. Final notebook runtime verification remains pending.','implementation diagram')
save_json(OUT/'figure-manifest.json',{'figures':figures,'inputs':sources,'snapshot':'2026-11-06','recorded':4,'planned':24})
print(json.dumps({'figures':len(figures),'source_files':len(sources),'output':str(OUT)}))
