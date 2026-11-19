from pathlib import Path
import json,hashlib,collections
R=Path(__file__).resolve().parent;O=R/'analysis';M=json.loads((O/'partitions.json').read_text());D={n:(R/n).read_bytes() for n in M};out={'vectors':[],'cross_payload_prefix_matches':[],'aux_reuse':[]}
for n,rows in M.items():
 r=next(r for r in rows if r['name']=='ipu_data');off=r['offset']+512;c=D[n][off:off+r['size']]
 out['vectors'].append({'file':n,'partition':'ipu_data','file_offset':off,'size':r['size'],'stored_sha256':r['stored_sha256'],'expected_zero_sha256':hashlib.sha256(bytes(r['size'])).hexdigest(),'aux16':r['aux16'],'ciphertext_first64':c[:64].hex(),'ciphertext_sha256':hashlib.sha256(c).hexdigest(),'interpretation':'If SHA256 describes plaintext and protection is XOR-stream based, ciphertext is keystream for this partition only; neither assumption proves the cipher.'})
 for nn,rrs in M.items():
  for rr in rrs:
   if rr['flags']!=3:continue
   cc=D[nn][rr['offset']+512:rr['offset']+512+rr['size']]
   for start in [0,16,256,4096]:
    needle=c[start:start+16];p=cc.find(needle)
    if p>=0 and not(n==nn and rr['name']=='ipu_data' and p==start):out['cross_payload_prefix_matches'].append({'source':n+':ipu_data','source_offset':start,'target':nn+':'+rr['name'],'target_offset':p})
seen=collections.defaultdict(list)
for n,rows in M.items():
 for r in rows:
  if r['flags']==3:seen[r['aux16']].append(n+':'+r['name'])
out['aux_reuse']=[{'aux16':k,'partitions':v} for k,v in seen.items() if len(v)>1]
(O/'known_plaintext_vectors.json').write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out,indent=2))
