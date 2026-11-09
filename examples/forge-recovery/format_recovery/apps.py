"""Original offline laboratory readers. Only minified output goes to agents."""
COMMON = r'''
const zlib = require('zlib');
function checksum(b) { let c=0xffffffff; for(const x of b){c^=x;for(let k=0;k<8;k++)c=(c>>>1)^((c&1)?0xedb88320:0);}return (c^0xffffffff)>>>0; }
class Cursor {
 constructor(b){this.b=b;this.p=0;}
 bytes(n){if(!Number.isInteger(n)||n<0||this.p+n>this.b.length)throw Error('range');const v=this.b.subarray(this.p,this.p+n);this.p+=n;return v;}
 u8(){return this.bytes(1)[0];} u16(){return this.bytes(2).readUInt16LE();}
 u32(){return this.bytes(4).readUInt32LE();} i32(){return this.bytes(4).readInt32LE();}
 varint(){let v=0,m=1;for(let k=0;k<5;k++){const b=this.u8();v+=(b&127)*m;if(!(b&128))return v;m*=128;}throw Error('varint');}
 signed(){const v=this.varint();return v%2?-(v+1)/2:v/2;}
 text(){return new TextDecoder('utf-8',{fatal:true}).decode(this.bytes(this.varint()));}
 end(){if(this.p!==this.b.length)throw Error('trailing');}
}
function unpack(b,magic){const c=new Cursor(b);if(c.bytes(4).toString()!==magic)throw Error('magic');const version=c.u8(),flags=c.u8(),count=c.u16(),length=c.u32(),crc=c.u32();if(version!==1&&version!==2)throw Error('version');if(flags&~3)throw Error('flags');const body=c.bytes(length);c.end();if(checksum(body)!==crc)throw Error('checksum');return {version,flags,count,body};}
function dictionary(c){const a=[];for(let n=c.varint();n--;){a.push(c.text());}return a;}
function label(a,i){if(i>=a.length)throw Error('label');return a[i];}
module.exports={Cursor,unpack,dictionary,label,inflate:b=>zlib.inflateSync(b)};
'''

READERS = {
'chunks': r'''
const {Cursor,unpack,inflate}=require('./binary');
function decode(data){const h=unpack(data,'CHNK'),c=new Cursor(h.body),n=c.u8(),entries=[];for(let i=0;i<n;i++)entries.push({slot:c.u16(),count:c.u16(),offset:c.u32(),length:c.u32()});const start=c.p;const records=[],seen=new Set(),ranges=[];
for(const e of entries){if(seen.has(e.slot))throw Error('duplicate slot');seen.add(e.slot);if(e.offset<start||e.offset+e.length>h.body.length)throw Error('chunk range');ranges.push([e.offset,e.offset+e.length]);const d=new Cursor(inflate(h.body.subarray(e.offset,e.offset+e.length))),rows=[];
for(let j=0;j<e.count;j++){const id=d.u32(),name=d.text(),raw=d.i32(),state=d.u8();if(state>1)throw Error('state');rows.push({id,label:name,value:h.version===2?-raw:raw,active:!!state});}d.end();records.push({slot:e.slot,rows});}
ranges.sort((a,b)=>a[0]-b[0]);let end=start;for(const r of ranges){if(r[0]!==end)throw Error('chunk coverage');end=r[1];}if(end!==h.body.length)throw Error('chunk tail');records.sort((a,b)=>a.slot-b.slot);const flat=records.flatMap(x=>x.rows);if(flat.length!==h.count)throw Error('count');if(h.flags&1)flat.reverse();return {version:h.version,records:flat};}
module.exports={decode};
''',
'journal': r'''
const {Cursor,unpack,dictionary,label}=require('./binary');
function decode(data){const h=unpack(data,'JRNL'),c=new Cursor(h.body),names=dictionary(c);let state=new Map(),pending=null;for(let i=0;i<h.count;i++){const op=c.u8();let target=pending||state;
if(op===1){const id=c.varint(),name=label(names,c.varint()),delta=c.signed(),bits=c.u8();if(bits>1)throw Error('state');const old=target.get(id);target.set(id,{id,label:name,value:(h.version===2&&old?old.value:0)+delta,active:!!bits});}
else if(op===2){target.delete(c.varint());}
else if(op===3){if(pending)throw Error('nested');pending=new Map(state);}
else if(op===4){if(!pending)throw Error('commit');state=pending;pending=null;}
else if(op===5){if(!pending)throw Error('abort');pending=null;}
else throw Error('opcode');}
c.end();if(pending)throw Error('open transaction');const records=[...state.values()].sort((a,b)=>a.id-b.id);if(h.flags&1)records.reverse();return {version:h.version,records};}
module.exports={decode};
''',
'columns': r'''
const {Cursor,unpack,dictionary,label,inflate}=require('./binary');
function decode(data){const h=unpack(data,'COLM'),c=new Cursor(h.flags&2?inflate(h.body):h.body),names=dictionary(c),ids=[],values=[],labels=[];let current=0;for(let i=0;i<h.count;i++){current+=c.varint();ids.push(current);}function readValues(){let v=0;for(let i=0;i<h.count;i++){v+=c.signed();values.push(v);}}function readLabels(){for(let i=0;i<h.count;i++)labels.push(label(names,c.varint()));}
if(h.version===1){readLabels();readValues();}else{readValues();readLabels();}const bits=c.bytes(Math.ceil(h.count/8));if(h.count%8&&bits.length&&(bits[bits.length-1]>>(h.count%8)))throw Error('padding');c.end();const records=ids.map((id,i)=>({id,label:labels[i],value:values[i],active:!!(bits[i>>3]&(1<<(i%8)))}));if(h.flags&1)records.reverse();return {version:h.version,records};}
module.exports={decode};
''',
'tree': r'''
const {Cursor,unpack,inflate}=require('./binary');
function decode(data){const h=unpack(data,'TREE'),c=new Cursor(h.body),nodes=new Map();for(let i=0;i<h.count;i++){const id=c.varint(),parent=c.varint(),kind=c.u8(),name=c.text(),flags=c.u8();if(!id||nodes.has(id)||kind>1||flags>1||name.includes('/'))throw Error('node');let value=0;if(kind===1){const raw=inflate(c.bytes(c.varint()));if(raw.length!==4)throw Error('value');value=h.version===1?raw.readInt32LE():raw.readInt32BE();}nodes.set(id,{id,parent,kind,name,flags,value});}c.end();
function resolve(n,seen){if(seen.has(n.id))throw Error('cycle');seen.add(n.id);if(!n.parent)return {path:n.name,hidden:!!n.flags};const p=nodes.get(n.parent);if(!p||p.kind!==0)throw Error('parent');const r=resolve(p,seen);return {path:r.path+'/'+n.name,hidden:r.hidden||!!n.flags};}
const records=[];for(const n of nodes.values()){const p=resolve(n,new Set());if(n.kind===1)records.push({id:n.id,label:p.path,value:n.value,active:!p.hidden});}records.sort((a,b)=>a.label<b.label?-1:a.label>b.label?1:a.id-b.id);if(h.flags&1)records.reverse();return {version:h.version,records};}
module.exports={decode};
''',
'qualification': r'''
const {Cursor,unpack}=require('./binary');
function decode(data){const h=unpack(data,'QUAL'),c=new Cursor(h.body),records=[];for(let i=0;i<h.count;i++){const id=c.u16(),label=c.text(),value=c.i32(),active=c.u8();if(active>1)throw Error('state');records.push({id,label,value,active:!!active});}c.end();return {version:h.version,records};}
module.exports={decode};
'''}
ENTRY = r'''
const fs=require('fs');const {decode}=require('./reader');
try {process.stdout.write(JSON.stringify(decode(fs.readFileSync(process.argv[2])))+'\n');}
catch(e){process.stderr.write(e.message+'\n');process.exitCode=2;}
'''
