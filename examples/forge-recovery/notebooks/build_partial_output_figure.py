"""Inspect the retained translucent-layer partial output; never run submitted code."""
from pathlib import Path
import argparse,json,hashlib,os
os.environ.setdefault('MPLCONFIGDIR','/tmp/rea-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['svg.fonttype']='none'
plt.rcParams['svg.hashsalt']='rea-recovery-partial-output'
import numpy as np
from PIL import Image
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
root=args.root.resolve();out=args.output.resolve()
out.mkdir(parents=True,exist_ok=True)
(out/'data').mkdir(exist_ok=True)
(out/'figures').mkdir(exist_ok=True)
aid='recovery-aa7c373605fd-opacity-rea-1';p=root/'experiment-v5/attempts'/aid
result=json.loads((p/'result.json').read_text());assert not result['checker']['passed']
assert result['checker']['cases']['visible']['decoder']['exit_code']==1
events=json.loads((p/'events.json').read_text())
rea_calls=sum(e['kind']=='tool' and e['tool']!='execute' for e in events)
assert rea_calls==0
original=root/'prepared-v2/oracle/opacity/visible/frame-003.png';candidate=p/'checks/visible/verified-output/frame_0003.png'
a,b=[np.array(Image.open(f).convert('RGBA')) for f in [original,candidate]];delta=abs(a.astype(int)-b.astype(int));mask=np.any(delta,axis=2)
changed=int(mask.sum());maximum=delta.max(axis=(0,1)).tolist();assert changed==50 and maximum==[1,1,1,0]
def checkerboard(a):
 h,w=a.shape[:2];yy,xx=np.indices((h,w));gray=np.where((xx//3+yy//3)%2,222,250)
 bg=np.stack([gray,gray,gray,np.full_like(gray,255)],axis=-1).astype('uint8')
 return Image.alpha_composite(Image.fromarray(bg),Image.fromarray(a))
fig,axes=plt.subplots(1,3,figsize=(10,4.5),layout='constrained');fig.set_facecolor('#fafbf9')
diff=np.where(mask[:,:,None],np.array([225,29,72]),np.array([241,245,249])).astype('uint8')
for ax,im,title in zip(axes,[checkerboard(a),checkerboard(b),diff],['Piskel reference','Partial decoder output','50 differing pixels']):
 ax.imshow(im,interpolation='nearest');ax.set_xticks([]);ax.set_yticks([]);ax.set_title(title,fontsize=13)
 for spine in ax.spines.values():spine.set_visible(False)
fig.suptitle('The largest RGB error is one level; 50 pixels differ',fontsize=18,fontweight='bold')
fig.supxlabel('Translucent-layer fixture · visible frame 4 · decoder exits 1 while generating HTML\nPartial output is not a completed recovery. This treatment made zero REA calls.',fontsize=11)
for ext in ['png','svg']:
 fig.savefig(out/f'figures/opacity-partial-output.{ext}',dpi=160,bbox_inches='tight',metadata={'Date':None} if ext=='svg' else None)
receipt={'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'attempt_id':aid,'input':'visible','frame_index':3,'changed_rgba_pixels':changed,'total_pixels':int(mask.size),'maximum_channel_delta_rgba':maximum,'decoder_exit_code':1,'decoder_stderr':result['checker']['cases']['visible']['decoder']['stderr'],'rea_calls':rea_calls,'source_sha256':{str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [original,candidate,p/'result.json',p/'events.json',p/'submission/decode.py']},'interpretation':'Observed exact pixel mismatch and decoder failure; no causal claim about the color difference mechanism or REA benefit'}
(out/'data/opacity-pixel-example.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
