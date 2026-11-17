"""Independent Python encoders and semantic expectations for original JS readers."""
from __future__ import annotations
import json, random, struct, zlib
from pathlib import Path
from apps import COMMON, READERS, ENTRY

CASES=('chunks','journal','columns','tree')
MAGIC={'chunks':b'CHNK','journal':b'JRNL','columns':b'COLM','tree':b'TREE','qualification':b'QUAL'}
def var(n):
    assert 0<=n<2**32
    out=bytearray()
    while n>=128:out.append((n&127)|128);n>>=7
    out.append(n);return bytes(out)
def signed(n):return var(2*n if n>=0 else -2*n-1)
def text(s):
    b=s.encode();return var(len(b))+b
def pack(case,version,flags,count,body):
    return MAGIC[case]+struct.pack('<BBHII',version,flags,count,len(body),zlib.crc32(body))+body
def dictionary(names):return var(len(names))+b''.join(text(x) for x in names)

def make(case,seed,n,version,flags):
    rng=random.Random(seed)
    names=['oak','café','東京','', 'rivet-Δ', 'leaf', 'with space']
    rows=[{'id':5+i*7,'label':names[(i+seed)%len(names)],'value':rng.randint(-9000,9000),'active':(i+seed)%3!=0} for i in range(n)]
    if case=='chunks':
        groups=[rows[i:i+3] for i in range(0,n,3)]
        blobs=[zlib.compress(b''.join(struct.pack('<I',r['id'])+text(r['label'])+struct.pack('<iB',-r['value'] if version==2 else r['value'],r['active']) for r in g)) for g in groups]
        physical=list(range(len(groups)));rng.shuffle(physical);offset=1+12*len(groups);entries={};body=b''
        for i in physical:entries[i]=struct.pack('<HHII',i,len(groups[i]),offset,len(blobs[i]));body+=blobs[i];offset+=len(blobs[i])
        order=list(range(len(groups)));rng.shuffle(order)
        payload=bytes([len(groups)])+b''.join(entries[i] for i in order)+body
        count=n
    elif case=='columns':
        ids=b'';last=0
        for r in rows:ids+=var(r['id']-last);last=r['id']
        values=b'';last=0
        for r in rows:values+=signed(r['value']-last);last=r['value']
        labels=b''.join(var(names.index(r['label'])) for r in rows)
        bits=bytearray((n+7)//8)
        for i,r in enumerate(rows):bits[i//8]|=int(r['active'])<<(i%8)
        payload=dictionary(names)+ids+(labels+values if version==1 else values+labels)+bits
        if flags&2:payload=zlib.compress(payload)
        count=n
    elif case=='journal':
        # Expected state is constructed from intended operations independently of the JS reader.
        ops=[];state={}
        def put(r):
            old=state.get(r['id']);delta=r['value']-(old['value'] if version==2 and old else 0)
            ops.append(b'\x01'+var(r['id'])+var(names.index(r['label']))+signed(delta)+bytes([r['active']]))
            state[r['id']]=dict(r)
        for r in rows:put(r)
        if rows:
            ops.append(b'\x03');saved={k:dict(v) for k,v in state.items()}
            changed={**rows[0],'value':rows[0]['value']+137,'active':False};put(changed)
            ops.append(b'\x05');state=saved
            ops.append(b'\x03');put({**rows[-1],'value':rows[-1]['value']-231,'label':'東京'})
            ops.append(b'\x04')
            if n>1:ops.append(b'\x02'+var(rows[0]['id']));state.pop(rows[0]['id'])
        payload=dictionary(names)+b''.join(ops);count=len(ops);rows=sorted(state.values(),key=lambda x:x['id'])
    elif case=='tree':
        nodes=[(1,0,0,'root',int(seed%2==0),None),(2,1,0,'branch',0,None)]
        expected=[]
        for i,r in enumerate(rows):
            name=r['label'] or 'empty-name';name+=str(i)
            parent=2 if i%2 else 0
            nodes.append((r['id'],parent,1,name,int(not r['active']),r['value']))
            expected.append({**r,'label':('root/branch/' if parent else '')+name,'active':r['active'] and not(parent and seed%2==0)})
        rng.shuffle(nodes);parts=[]
        for id,parent,kind,name,hidden,value in nodes:
            part=var(id)+var(parent)+bytes([kind])+text(name)+bytes([hidden])
            if kind:
                raw=zlib.compress(struct.pack('<i' if version==1 else '>i',value));part+=var(len(raw))+raw
            parts.append(part)
        payload=b''.join(parts);count=len(nodes);rows=sorted(expected,key=lambda r:(r['label'],r['id']))
    elif case=='qualification':
        payload=b''.join(struct.pack('<H',r['id'])+text(r['label'])+struct.pack('<iB',r['value'],r['active']) for r in rows);count=n
    else:raise ValueError(case)
    if flags&1 and case!='qualification':rows=list(reversed(rows))
    return pack(case,version,flags,count,payload),{'version':version,'records':rows}

def negatives(case,raw):
    bad=[]
    bad.append(('magic',b'????'+raw[4:]))
    bad.append(('truncated',raw[:-1]))
    b=bytearray(raw);b[12]^=1;bad.append(('checksum',bytes(b)))
    b=bytearray(raw);b[4]=3;bad.append(('version',bytes(b)))
    bad.append(('trailing',raw+b'\x00'))
    b=bytearray(raw);b[5]=128;bad.append(('flags',bytes(b)))
    # Valid checksum with truncated payload distinguishes semantic parsing from checksum-only rejection.
    bad.append(('payload',pack(case,raw[4],raw[5],struct.unpack_from('<H',raw,6)[0],raw[16:-1])))
    return bad

def prepare(root:Path):
    if root.exists():raise ValueError('Use a fresh prepared directory')
    for case in (*CASES,'qualification'):
        source=root/'source'/case;source.mkdir(parents=True)
        for name,code in [('binary.js',COMMON),('reader.js',READERS[case]),('index.js',ENTRY)]: (source/name).write_text(code)
        inputs=root/'inputs'/case;inputs.mkdir(parents=True)
        (inputs/'README.txt').write_text('Original offline laboratory application. Reconstruct the file reader as standalone Python. app/ contains the minified shipped reader when supplied. sample files and matching JSON show the output contract. Source, source maps, and hidden checks are withheld.\n')
        for i,(seed,n,version,flags) in enumerate(((17,4,1,0),(29,7,2,3))):
            raw,out=make(case,seed,n,version,flags)
            (inputs/f'sample-{i}.bin').write_bytes(raw);(inputs/f'sample-{i}.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
        tests=[]
        for i in range(12):
            version=i%2+1;n=(0,1,7,13,40,3)[i//2];seed=109+i*13
            flags=(i//2+i%2)%4
            raw,out=make(case,seed,n,version,flags)
            folder=root/'oracle'/case;folder.mkdir(parents=True,exist_ok=True)
            name=f'heldout-{i:02}.bin';(folder/name).write_bytes(raw)
            tests.append({'name':name,'valid':True,'expected':out,'dimensions':{'records_before_replay':n,'version':version,'flags':flags}})
        raw,_=make(case,811,7,2,3)
        for name,b in negatives(case,raw):
            path=f'invalid-{name}.bin';(folder/path).write_bytes(b);tests.append({'name':path,'valid':False})
        (folder/'cases.json').write_text(json.dumps(tests,ensure_ascii=False,indent=2)+'\n')
