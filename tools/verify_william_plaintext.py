from pathlib import Path
import urllib.request,urllib.parse,json,hashlib,collections
R=Path(__file__).resolve().parent;O=R/'analysis'/'william_review';P=O/'plaintext_samples';P.mkdir(exist_ok=True)
M=json.loads((R/'analysis'/'partitions.json').read_text());D={n:(R/n).read_bytes() for n in M}
commit='660247dc05e68d0645d96984437a3dade0b2c076';base=f'https://raw.githubusercontent.com/williamwu1234/S5-reverse-engineering/{commit}/'
results=[]
for name in ['eep_act_a','eep_act_b','ipu_data','koutei_kao','music']:
 remote=f'04_关键数据/K32恢复明文/rec_S5V29_{name}_from_G100.bin';url=base+urllib.parse.quote(remote,safe='/');p=P/Path(remote).name
 if p.exists():
  data=p.read_bytes()
 else:
  expected=next(e['size'] for e in M['S5___V29.bin'] if e['name']==name)
  pieces=[]
  for start in range(0,expected,524288):
   end=min(start+524288,expected)-1
   req=urllib.request.Request(url,headers={'Range':f'bytes={start}-{end}'})
   with urllib.request.urlopen(req,timeout=60) as response:
    chunk=response.read(end-start+1)
    if response.status!=206:
     raise RuntimeError('Server did not honor byte-range request; refusing to treat full response as a chunk')
   if len(chunk)!=end-start+1:raise RuntimeError('Incomplete chunk')
   pieces.append(chunk)
  data=b''.join(pieces)
  p.write_bytes(data)
 h=hashlib.sha256(data).hexdigest();row={'name':name,'url':url,'bytes':len(data),'sha256':h,'nonzero_bytes':sum(x!=0 for x in data),'local_versions':[]}
 for fn,entries in M.items():
  e=next(e for e in entries if e['name']==name)
  cipher=D[fn][e['offset']+512:e['offset']+512+e['size']]
  row['local_versions'].append({'file':fn,'size_matches':len(data)==e['size'],'stored_sha256_matches':h==e['stored_sha256'],'ciphertext_sha256':hashlib.sha256(cipher).hexdigest()})
 results.append(row)
 print(name,len(data),'sha',h,'local matches',[(x['file'],x['stored_sha256_matches']) for x in row['local_versions']])
(O/'plaintext_verification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
