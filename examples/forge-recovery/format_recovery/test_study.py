import json,sys
import os
import pytest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from fixtures import make,negatives,CASES
from checker import classify

def test_semantic_grade_rejects_wrong_order_and_types():
    expected={'version':1,'records':[{'id':1,'label':'x','value':2,'active':True},{'id':3,'label':'y','value':4,'active':False}]}
    execution={'exit_code':0,'stdout':json.dumps(expected),'stderr':''}
    assert classify(execution,expected)['passed']
    wrong={**expected,'records':list(reversed(expected['records']))}
    assert not classify({**execution,'stdout':json.dumps(wrong)},expected)['passed']
    wrong=json.loads(json.dumps(expected));wrong['records'][0]['active']=1
    assert not classify({**execution,'stdout':json.dumps(wrong)},expected)['passed']
    assert not classify({**execution,'exit_code':1},expected)['passed']

def test_rejection_excludes_killed_and_timed_out_programs():
    for code in (0,124,137):assert not classify({'exit_code':code,'stdout':'','stderr':'bad'})['passed']
    assert classify({'exit_code':2,'stdout':'','stderr':'invalid'})['passed']
    assert not classify({'exit_code':2,'stdout':'','stderr':''})['passed']

def test_fixture_boundaries_are_real_controls():
    for case in CASES:
        empty,expected=make(case,109,0,1,0)
        assert expected['records']==[]
        raw,expected=make(case,122,13,2,3)
        assert expected['records'] and raw!=empty
        assert any(not r['active'] for r in expected['records'])
        assert len(negatives(case,raw))==7
        assert all(b!=raw for _,b in negatives(case,raw))

@pytest.mark.skipif(not os.environ.get('FORMAT_PREPARED'),reason='Explicit prepared fixtures and retained checker image required')
def test_real_python_checker_positive_and_reject_everything(tmp_path):
    from checker import evaluate
    from forge_recovery.common import read_json
    prepared=Path(os.environ['FORMAT_PREPARED'])
    image=read_json(prepared.parent/'format-recovery-build/retained-images.json')['images']['checker']
    source=tmp_path/'positive';source.mkdir()
    (source/'decode.py').write_text('''import json,struct,sys,zlib
b=open(sys.argv[1],'rb').read()
try:
 magic,version,flags,count,length,crc=struct.unpack('<4sBBHII',b[:16]);body=b[16:]
 assert magic==b'QUAL' and version in (1,2) and flags<4 and len(body)==length and zlib.crc32(body)==crc
 p=0;rows=[]
 for i in range(count):
  id=struct.unpack_from('<H',body,p)[0];p+=2;n=0;shift=0
  while True:
   x=body[p];p+=1;n|=(x&127)<<shift;shift+=7
   if x<128:break
  label=body[p:p+n].decode();p+=n;value,active=struct.unpack_from('<iB',body,p);p+=5
  assert active in (0,1)
  rows.append(dict(id=id,label=label,value=value,active=bool(active)))
 assert p==len(body)
 print(json.dumps(dict(version=version,records=rows)))
except Exception:
 print('invalid input',file=sys.stderr);sys.exit(2)
''')
    result=evaluate(source,prepared,'qualification',tmp_path/'positive-check',image)
    assert result['passed'] and result['valid_passed']==12 and result['invalid_passed']==7
    bad=tmp_path/'negative';bad.mkdir()
    (bad/'decode.py').write_text("import sys\nprint('invalid input',file=sys.stderr)\nsys.exit(2)\n")
    result=evaluate(bad,prepared,'qualification',tmp_path/'negative-check',image)
    assert not result['passed'] and result['valid_passed']==0 and result['invalid_passed']==0
