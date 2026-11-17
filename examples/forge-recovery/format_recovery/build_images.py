"""Build and immediately retain exact images; release only owned receipts later."""
import json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;EXAMPLE=HERE.parent
sys.path.insert(0,str(EXAMPLE/'src'))
from forge_recovery.sandbox import Sandbox
from forge_recovery.common import write_json
root=EXAMPLE/'.local/format-recovery-build'
if (root/'retained-images.json').exists() or any((root/'retention').glob('*.container.json')):
    raise RuntimeError('Existing image ownership records must be reconciled; use a fresh build directory without overwriting receipts')
images={};receipts={}
roles={'base':(EXAMPLE/'containers/Dockerfile.base',EXAMPLE/'containers','rea-forge-recovery-base:v1'),
    'rea':(EXAMPLE/'containers/Dockerfile.rea',root,'rea-forge-recovery-rea:v1'),
    'build':(HERE/'Dockerfile.build',HERE,'rea-format-build:v1'),
    'checker':(HERE/'Dockerfile.checker',EXAMPLE/'containers','rea-format-checker:v1')}
for role,(dockerfile,context,tag) in roles.items():
    iid=root/(role+'.iid')
    with (root/(role+'-build.log')).open('w') as log:
        subprocess.run(['docker','build','--iidfile',str(iid),'-t',tag,'-f',str(dockerfile),str(context)],stdout=log,stderr=subprocess.STDOUT,check=True)
    image=iid.read_text().strip()
    box=Sandbox(root/'retention'/role,root,image=image,owner='format-study-build-retention-'+role)
    box.start();images[role]=image;receipts[role]=str(box.receipt)
    write_json(root/'retained-images.json',{'images':images,'receipts':receipts})
    print(json.dumps({'retained':role,'image':image,'receipt':str(box.receipt)}),flush=True)
