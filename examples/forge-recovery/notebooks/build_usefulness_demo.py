"""Explain the recovered deliverable using retained pixels; never execute submissions."""
from pathlib import Path
import argparse, hashlib, json, shutil
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

p=argparse.ArgumentParser();p.add_argument('article_root',type=Path);args=p.parse_args()
P=args.article_root;P.mkdir(parents=True,exist_ok=True);(P/'assets').mkdir(exist_ok=True);(P/'data').mkdir(exist_ok=True)
E=Path(__file__).resolve().parents[1]/'.local'
A=E/'experiment-v5/attempts/recovery-aa7c373605fd-basic-rea-2/checks/heldout/verified-output'
O=E/'prepared-v2/oracle/basic/heldout'
meta=json.loads((A/'manifest.json').read_text());assert len(meta['frames'])==9 and meta['fps']==13
inputs={};outputs={}
def copied(src,dst):
    inputs[str(src)]=hashlib.sha256(src.read_bytes()).hexdigest();shutil.copy2(src,dst)
    outputs[str(dst.relative_to(P))]=hashlib.sha256(dst.read_bytes()).hexdigest()
for i,name in enumerate(meta['frames']):
    with Image.open(A/name) as a,Image.open(O/f'frame-{i:03}.png') as b:
        assert a.convert('RGBA').tobytes()==b.convert('RGBA').tobytes()
    copied(A/name,P/'assets'/f'demo-frame-{i}.png')
copied(A/'spritesheet.png',P/'assets/demo-spritesheet.png')
copied(O/'animation.piskel',P/'assets/demo-input.piskel')

plt.rcParams.update({'font.family':'DejaVu Sans','text.color':'#202c3b','figure.facecolor':'#fbfbf8'})
fig=plt.figure(figsize=(11,5.2),layout='constrained')
grid=fig.add_gridspec(2,2,height_ratios=[4,1.5],width_ratios=[1,1.25])
left=fig.add_subplot(grid[0,0]);left.axis('off')
left.text(0,1,'INPUT: a saved animation file',va='top',fontsize=17,weight='bold')
left.text(0,.8,'JSON, image chunks and frame indexes',fontsize=12)
left.text(.02,.62,'{\n  "piskel": {\n    "width": 24,\n    "height": 24,\n    "fps": 13,\n    "layers": ["{…image data…}"]\n  }\n}',va='top',family='monospace',fontsize=13,bbox={'facecolor':'#e9eeef','edgecolor':'none','pad':16})
left.text(0,-.05,'Excerpt, abbreviated for display',fontsize=10,color='#566570')
right=fig.add_subplot(grid[0,1]);right.set_facecolor('#152330')
with Image.open(A/meta['frames'][0]) as im: right.imshow(im.convert('RGBA'),interpolation='nearest')
right.set_xticks([]);right.set_yticks([])
right.set_title('OUTPUT: a reusable decoder\nand viewable PNG frames',fontsize=17,weight='bold',pad=10)
strip=fig.add_subplot(grid[1,:]);strip.set_facecolor('#152330')
with Image.open(A/'spritesheet.png') as im: strip.imshow(im.convert('RGBA'),interpolation='nearest')
strip.set_xticks([12+24*i for i in range(9)],[str(i+1) for i in range(9)],fontsize=11);strip.set_yticks([])
strip.set_title('Exported sprite sheet · nine frames in playback order · 216 × 24 pixels',fontsize=13,pad=10)
for ax in (right,strip):
    for spine in ax.spines.values(): spine.set_visible(False)
fig.savefig(P/'assets/recovery-deliverable.png',dpi=160,bbox_inches='tight');fig.savefig(P/'assets/recovery-deliverable.svg',bbox_inches='tight');plt.close(fig)

html='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' data:; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'"><title>From saved file to recovered frames</title><style>
*{box-sizing:border-box}body{margin:0;padding:20px;background:#f1f4f2;color:#1d303c;font:15px/1.5 system-ui}h1{font-size:24px;line-height:1.2;margin:0 0 8px}p{margin:8px 0}header p{color:#52616d}.columns{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:18px}h2{font-size:15px;margin:0 0 10px}pre{font:12px/1.65 ui-monospace,monospace;padding:14px;border:1px solid #c5d0d5;background:white;overflow:auto}.stage{background:repeating-conic-gradient(#182c38 0% 25%,#203743 0% 50%) 50%/32px 32px;border-radius:5px}.stage img{display:block;width:min(100%,260px);height:auto;image-rendering:pixelated;margin:auto}.controls{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:14px 0}button,select,.download{font:600 13px system-ui;padding:9px 12px;border:1px solid #8ea5ab;border-radius:4px;background:white;color:#1d4149;cursor:pointer}button:focus-visible,select:focus-visible,a:focus-visible,input:focus-visible{outline:3px solid #d47c2e;outline-offset:2px}button[aria-pressed="true"]{background:#1d5e65;color:white}label{font-size:13px}input{width:100%}.strip{display:grid;grid-template-columns:repeat(9,1fr);gap:5px;margin:12px 0}.strip button{padding:3px;border-width:2px}.strip img{width:100%;image-rendering:pixelated;background:#182c38}.strip span{display:block;font-size:11px}.download{display:inline-block;text-decoration:none}.small{font-size:12px;color:#52616d}.match{font-weight:600;color:#176050}#status{font-variant-numeric:tabular-nums}.export{margin-top:18px;border-top:1px solid #cad4d8;padding-top:14px}.export img{width:100%;image-rendering:pixelated;background:#182c38;display:block;margin:10px 0}.legend{font-size:12px;color:#52616d} @media(max-width:540px){body{padding:14px}.columns{grid-template-columns:1fr;gap:12px}pre{font-size:11px;max-height:125px}.stage img{width:230px}.strip{gap:2px}.strip button{padding:1px}h1{font-size:21px}}
</style></head><body><header><h1>A file you can use again</h1><p>Scrub the decoded frames, inspect the changes, or download the agent's sprite sheet.</p></header><div class="columns"><section><h2>1. What the decoder receives</h2><pre>{
  "piskel": {
    "width": 24, "height": 24,
    "fps": 13,
    "layers": ["{…image data…}"]
  }
}</pre><p class="small">Abbreviated file structure. These are the nine unseen frames used to check the saved decoder.</p><a class="small" href="assets/demo-input.piskel" download="animation.piskel">Download the original fixture</a></section><section><h2>2. What it recovered</h2><div class="stage"><img id="frame" src="assets/demo-frame-0.png" width="24" height="24" alt="Recovered frame 1 of 9"></div></section></div><div class="controls"><button id="play" type="button" aria-pressed="false">Play frames</button><label for="speed">Playback speed</label><select id="speed"><option value="3">Slow inspection · 3 FPS</option><option value="13">Recovered speed · 13 FPS</option></select><span id="status">Frame 1 / 9</span></div><label for="scrub">Frame</label><input id="scrub" type="range" min="0" max="8" value="0" step="1"><div class="strip" id="strip"></div><p class="match">Exact reference match: 576 / 576 pixels in each frame, including alpha.</p><p class="legend">The creature moves and fades; the magenta pixel also moves with the frame index. This makes ordering errors visible.</p><section class="export"><h2>3. Use the exported sprite sheet</h2><img src="assets/demo-spritesheet.png" width="216" height="24" alt="All nine recovered frames in one horizontal sprite sheet"><a class="download" href="assets/demo-spritesheet.png" download="recovered-spritesheet.png">Download sprite sheet · 216 × 24 PNG</a><p class="small">Recorded-output viewer built for this article. It reads the agent's checked PNGs; it does not execute the agent's code or call a model. The submitted browser preview passed a separate isolated check.</p></section><script>
const frame=document.getElementById('frame'),scrub=document.getElementById('scrub'),play=document.getElementById('play'),speed=document.getElementById('speed'),status=document.getElementById('status'),strip=document.getElementById('strip');let index=0,timer=null;
function render(){frame.src=`assets/demo-frame-${index}.png`;frame.alt=`Recovered frame ${index+1} of 9`;scrub.value=index;status.textContent=`Frame ${index+1} / 9`;[...strip.children].forEach((b,i)=>b.setAttribute('aria-pressed',String(i===index)));}
function pause(){clearInterval(timer);timer=null;play.textContent='Play frames';play.setAttribute('aria-pressed','false');}
function start(){pause();play.textContent='Pause frames';play.setAttribute('aria-pressed','true');timer=setInterval(()=>{index=(index+1)%9;render()},1000/Number(speed.value));}
for(let i=0;i<9;i++){const b=document.createElement('button');b.type='button';b.setAttribute('aria-label',`Select frame ${i+1}`);b.innerHTML=`<img src="assets/demo-frame-${i}.png" alt=""><span>${i+1}</span>`;b.addEventListener('click',()=>{pause();index=i;render()});strip.appendChild(b)}
play.addEventListener('click',()=>timer?pause():start());scrub.addEventListener('input',()=>{pause();index=Number(scrub.value);render()});speed.addEventListener('change',()=>{if(timer)start()});document.addEventListener('visibilitychange',()=>{if(document.hidden)pause()});render();
</script></body></html>'''
(P/'animation-demo.html').write_text(html)
write={'attempt':'recovery-aa7c373605fd-basic-rea-2','source_files':inputs,'copied_outputs':outputs,'display_only':True,'executes_submitted_code':False,'inference':False,'dimensions':[24,24],'frames':9,'recorded_fps':13,'default_inspection_fps':3,'derived_figures':['assets/recovery-deliverable.png','assets/recovery-deliverable.svg'],'figure_limit':'Abbreviated JSON shows structure; output pixels and exported sheet are retained agent files.'}
(P/'data/usefulness-demo.json').write_text(json.dumps(write,indent=2)+'\n')
print(P/'animation-demo.html')
