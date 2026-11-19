from pathlib import Path
import struct,hashlib,json,csv,math,collections,zlib
R=Path(__file__).resolve().parent; O=R/'analysis'
allrows={}
for name in ['S5___V28.bin','S5___V29.bin']:
 b=(R/name).read_bytes(); count=struct.unpack_from('<I',b,0x2e8)[0]; rows=[]
 for i in range(count):
  p=0x2ec+92*i; label=b[p:p+12].split(b'\0')[0].decode('ascii'); off,size,target,flags=struct.unpack_from('<4I',b,p+12); digest=b[p+28:p+60].hex(); aux=b[p+60:p+76].hex()
  matches=[]
  for base in [0,0x200]:
   d=b[base+off:base+off+size]
   if hashlib.sha256(d).hexdigest()==digest: matches.append(base)
  d=b[off+0x200:off+0x200+size]; n=len(d); c=collections.Counter(d)
  ent=-sum((v/n)*math.log2(v/n) for v in c.values()) if n else 0
  rows.append({'index':i,'name':label,'offset':off,'size':size,'target_or_logical_offset':target,'flags':flags,'stored_sha256':digest,'aux16':aux,'sha256_matching_bases':matches,'entropy_base_0x200':ent,'head16_base_0x200':d[:16].hex()})
 allrows[name]=rows
 print(name,'partition count',count,'bounds end',hex(max(x['offset']+x['size']+512 for x in rows)), 'file',hex(len(b)))
 for r in rows: print(r['name'],hex(r['offset']),hex(r['size']),r['flags'],'hash bases',r['sha256_matching_bases'],'H',round(r['entropy_base_0x200'],4))
 print('CRC32 body',hex(zlib.crc32(b[512:])), 'field40',b[64:68].hex())
(O/'partitions.json').write_text(json.dumps(allrows,indent=2),encoding='utf-8')
comp=[]
for x,y in zip(*allrows.values()):
 comp.append({'name':x['name'],'offset':hex(x['offset']),'size':x['size'],'flags':x['flags'],'stored_sha256_equal':x['stored_sha256']==y['stored_sha256'],'aux16_equal':x['aux16']==y['aux16']})
with (O/'partition_comparison.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.DictWriter(f,fieldnames=comp[0].keys());w.writeheader();w.writerows(comp)
print('CHANGED stored hashes:',[r['name'] for r in comp if not r['stored_sha256_equal']])
