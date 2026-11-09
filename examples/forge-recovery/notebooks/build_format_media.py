"""Static figures from frozen recorded outcomes; never runs inference or decoders."""
import argparse,csv,hashlib,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D

def main(root,out):
    comp=json.loads((root/'comparison.json').read_text());out.mkdir(parents=True,exist_ok=True)
    arms=['baseline','rea','data_only'];names={'baseline':'Application + ordinary tools','rea':'Application + REA','data_only':'Samples only (diagnostic)'}
    cases=list(dict.fromkeys(m['fixture'] for m in comp['measurements']))
    labels={'chunks':'Compressed chunks','journal':'Transactional journal','columns':'Column encoding','tree':'Hierarchical archive'}
    rows=[(c,r) for c in cases for r in (1,2,3)]
    by={(m['fixture'],m['repetition'],m['arm']):m for m in comp['measurements']}
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'#fafaf7','axes.facecolor':'#fafaf7'})
    fig,ax=plt.subplots(figsize=(11,8.5));ax.set_xlim(-1.8,3);ax.set_ylim(-.8,len(rows)+1.4);ax.axis('off')
    ax.text(-1.75,len(rows)+1.15,'Can the saved decoder read files it has never seen?',fontsize=17,weight='bold')
    ax.text(-1.75,len(rows)+.65,'12 unseen valid inputs per attempt · 4 laboratory formats · 3 repetitions',fontsize=10,color='#505761')
    headers={'baseline':'Application +\nordinary tools','rea':'Application +\nREA','data_only':'Samples only\n(diagnostic)'}
    for j,a in enumerate(arms):ax.text(j+.45,len(rows)+.05,headers[a],ha='center',fontsize=10,weight='bold',linespacing=1.1)
    for i,(case,rep) in enumerate(rows):
        y=len(rows)-i-1
        ax.text(-1.75,y+.45,f'{labels[case]} · {rep}',va='center',fontsize=10)
        for j,arm in enumerate(arms):
            m=by[case,rep,arm];n=m['valid_passed'];negative=m['invalid_passed']
            color='#e4e6e9' if n is None else '#d8ebe0' if n==12 else '#f6e8ce' if n else '#f1dcd8'
            ax.add_patch(Rectangle((j,y+.05),.9,.83,facecolor=color,edgecolor='white',linewidth=1.5))
            text='Unavailable' if n is None else f'{n}/12 valid\n{negative}/7 invalid'
            ax.text(j+.45,y+.46,text,ha='center',va='center',fontsize=10,color='#202b34')
        if rep==3:ax.plot([-1.75,2.9],[y,y],color='#c7ccd0',lw=.7)
    ax.text(-1.75,-.45,'Green = all unseen valid inputs match. Invalid-input credit requires successful visible controls.\nEach cell is one attempt; repeated inputs are not independent new tasks. All scored attempts are shown.',fontsize=9,color='#505761',va='top')
    fig.savefig(out/'format-outcomes.png',dpi=180,bbox_inches='tight');fig.savefig(out/'format-outcomes.svg',bbox_inches='tight');plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,7),sharey=True)
    colors={'baseline':'#326a99','rea':'#227963','data_only':'#777d87'}
    for ax,metric,title in zip(axes,['task_tokens','agent_seconds'],['Total task tokens','Elapsed agent seconds']):
        for i,(case,rep) in enumerate(rows):
            b,t=by[case,rep,'baseline'],by[case,rep,'rea']
            if b[metric] is not None and t[metric] is not None:ax.plot([b[metric],t[metric]],[i,i],color='#aab1b7',lw=1)
            for arm,marker in [('baseline','o'),('rea','s'),('data_only','x')]:
                val=by[case,rep,arm][metric]
                if val is not None:ax.scatter(val,i,color=colors[arm],marker=marker,s=40,label=names[arm] if i==0 else None,zorder=3)
                elif metric=='task_tokens':
                    bound=by[case,rep,arm]['reported_tokens_lower_bound']
                    ax.scatter(bound,i,edgecolors=colors[arm],facecolors='none',marker='>',s=60,zorder=3)
        ax.set_title(title,loc='left',weight='bold');ax.grid(axis='x',color='#e1e4e5');ax.set_axisbelow(True)
        if metric=='task_tokens':ax.set_xscale('log');ax.set_xlabel('Tokens · logarithmic scale')
        else:ax.set_xlabel('Seconds')
    axes[0].set_yticks(range(len(rows)),[f'{labels[c]} · {r}' for c,r in rows]);axes[0].invert_yaxis()
    handles=[Line2D([],[],color=colors[a],marker=marker,linestyle='none',label=names[a]) for a,marker in [('baseline','o'),('rea','s'),('data_only','x')]]
    handles.append(Line2D([],[],color='#777d87',marker='>',markerfacecolor='none',linestyle='none',label='Reported lower bound; total unavailable'))
    fig.legend(handles=handles,loc='lower center',ncol=2,frameon=False,fontsize=9)
    fig.suptitle('What each attempt cost, including failures',x=.02,ha='left',fontsize=17,weight='bold')
    fig.text(.02,.09,'Lines join the main paired comparison. Samples-only is a separate diagnostic. Tokens include repeated context and schemas.\nHollow triangles show known token lower bounds when total usage is unavailable. Host timing is descriptive.',fontsize=9,color='#505761')
    fig.tight_layout(rect=(0,.16,1,.94));fig.savefig(out/'format-resources.png',dpi=180,bbox_inches='tight');fig.savefig(out/'format-resources.svg',bbox_inches='tight');plt.close(fig)
    with (out/'format-attempts.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(comp['measurements'][0]));writer.writeheader();writer.writerows(comp['measurements'])
    manifest={'source':str(root/'comparison.json'),'sha256':hashlib.sha256((root/'comparison.json').read_bytes()).hexdigest(),'experiment_id':comp['experiment_id'],'figures':{
        'format-outcomes.png':{'question':'Does each saved decoder recover unseen file behavior?','boundary':'Four original laboratory formats; all 36 attempts retained. No native-binary or universal REA claim.'},
        'format-resources.png':{'question':'What resource cost accompanies the paired outcomes?','boundary':'Provider tokens and local elapsed time; no remote CPU or billing attribution.'}}}
    (out/'format-media-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('output',type=Path);a=p.parse_args();main(a.root.resolve(),a.output.resolve())
