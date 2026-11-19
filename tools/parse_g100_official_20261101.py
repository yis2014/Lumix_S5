"""Validate and extract official G100 container as inert byte evidence."""
from pathlib import Path
import struct,hashlib,json,zlib,collections
import key_research_20261101 as K
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis/eeprom_keyhunt_20261101/g100_official'
P=OUT/'G100_V13.bin';D=OUT/'sections';D.mkdir(exist_ok=True)
b=P.read_bytes();source=json.loads((OUT/'official_sample_source.json').read_text(encoding='utf-8'))
assert len(b)==source['bin_bytes'] and K.sha(b)==source['bin_sha256']
assert b[:4]==b'UPD\0'
assert struct.unpack_from('<I',b,0x38)[0]==0x200
assert struct.unpack_from('<I',b,0x3c)[0]+0x200==len(b)
crc=zlib.crc32(b[0x200:]);assert crc==struct.unpack_from('<I',b,0x40)[0]
count=struct.unpack_from('<I',b,0x2e8)[0];assert 0<count<1024
rows=[];occ=collections.Counter()
for i in range(count):
    p=0x2ec+i*92;name=b[p:p+12].split(b'\0')[0].decode('ascii');o,n,target,flags=struct.unpack_from('<4I',b,p+12)
    start=o+0x200;end=start+n;assert 0<=start<=end<=len(b)
    data=b[start:end];digest=b[p+28:p+60].hex()
    fn=f'{i:02d}_{name}_{occ[name]}.bin';occ[name]+=1;path=D/fn
    if path.exists():assert path.read_bytes()==data
    else:
        with path.open('xb') as f:f.write(data)
    rows.append(dict(index=i,name=name,occurrence=occ[name]-1,table_offset=p,file_offset=start,end=end,size=n,
        target_unknown=target,flags=flags,directory_sha256=digest,payload_sha256=K.sha(data),digest_matches=K.sha(data)==digest,
        aux16=b[p+60:p+76].hex(),section_file=str(path.relative_to(ROOT)),entropy=float(K.np.round(K.np.nan_to_num(-sum(v/len(data)*K.np.log2(v/len(data)) for v in collections.Counter(data).values()) if data else 0),6))))
result=dict(file=str(P.relative_to(ROOT)),sha256=K.sha(b),size=len(b),platform=b[0xc:0x20].split(b'\0')[0].decode('ascii'),
    outer_field34=struct.unpack_from('<I',b,0x34)[0],count=count,crc32=hex(crc),
    digest_matching_count=sum(r['digest_matches'] for r in rows),entries=rows,
    note='Complete directory SHA matches demonstrate readable stored payloads in this official sample, not key equivalence with S5.')
(OUT/'container.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='entries'},ensure_ascii=False),flush=True)
for r in rows:print(r['index'],r['name'],hex(r['file_offset']),hex(r['size']),r['flags'],r['digest_matches'],r['entropy'],flush=True)
