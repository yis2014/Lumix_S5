from pathlib import Path
import hashlib,json,zlib,struct,collections
R=Path(__file__).resolve().parent;O=R/'analysis';M=json.loads((O/'partitions.json').read_text());res={'known_plaintext':[],'aux_checksum_matches':[],'header_digest_matches':[],'plaintext_runs':[]}
cache={}
for name,rows in M.items():
 b=(R/name).read_bytes()
 for r in rows:
  n=r['size']; off=r['offset']+512;d=b[off:off+n];aux=bytes.fromhex(r['aux16'])
  if n not in cache:
   cache[n]=[(v,hashlib.sha256(bytes([v])*n).hexdigest()) for v in [0,255]]
  for v,h in cache[n]:
   if h==r['stored_sha256']:res['known_plaintext'].append({'file':name,'partition':r['name'],'flags':r['flags'],'size':n,'fill_byte':v,'candidate':'constant-fill SHA256 exact match','ciphertext_head32':d[:32].hex(),'aux16':r['aux16']})
  checks={'crc32_ciphertext':zlib.crc32(d),'adler32_ciphertext':zlib.adler32(d)}
  for kind,c in checks.items():
   for i in range(0,13,4):
    for endian in ['little','big']:
     if int.from_bytes(aux[i:i+4],endian)==c:res['aux_checksum_matches'].append({'file':name,'partition':r['name'],'kind':kind,'aux_offset':i,'endian':endian,'value':hex(c)})
 # Check if 64-byte header field consists of obvious hashes over defined subregions
 h=b[0x220:0x260]
 for start,end,label in [(0x2a0,0x1600,'inner_header_table'),(0x2a0,len(b),'inner_header_and_payload'),(0x1600,len(b),'all_partition_data'),(0x200,len(b),'outer_body')]:
  dig=hashlib.sha256(b[start:end]).digest()
  for j in [0,32]:
   if h[j:j+32]==dig:res['header_digest_matches'].append([name,label,j])
 # Long constant runs within protected regions could expose clear subblocks
 for r in rows:
  if r['flags']!=3:continue
  d=b[r['offset']+512:r['offset']+512+r['size']]
  for value in [0,255]:
   needle=bytes([value])*32;pos=d.find(needle)
   if pos>=0:res['plaintext_runs'].append([name,r['name'],pos,value])
(O/'entrypoint_probe.json').write_text(json.dumps(res,indent=2),encoding='utf-8')
for k,v in res.items():print(k,json.dumps(v,ensure_ascii=False))
