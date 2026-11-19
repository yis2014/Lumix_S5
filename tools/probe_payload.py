from pathlib import Path
import json,hashlib,collections,math,struct,zlib
R=Path(__file__).resolve().parent;O=R/'analysis';meta=json.loads((O/'partitions.json').read_text()); blobs={n:(R/n).read_bytes() for n in meta}
def H(b):
 n=len(b);return -sum((v/n)*math.log2(v/n) for v in collections.Counter(b).values()) if n else 0
out={'aux_tests':[],'simple_transform_digest_matches':[],'equal_digest_pairs':[],'readable_strings':[],'payload_boundaries':[]}
# Test whether the 16-byte field is a ciphertext MD5, rather than assuming IV.
for name,rows in meta.items():
 b=blobs[name]
 for r in rows:
  pos=r['offset']+512;d=b[pos:pos+r['size']];aux=r['aux16']; digest=r['stored_sha256']
  candidates={'data_md5':hashlib.md5(d).hexdigest(),'sha256_first16':hashlib.sha256(d).hexdigest()[:32],'sha256_last16':hashlib.sha256(d).hexdigest()[32:]}
  out['aux_tests'].append({'file':name,'partition':r['name'],'matches':[k for k,v in candidates.items() if v==aux],'aux':aux})
  out['payload_boundaries'].append({'file':name,'partition':r['name'],'file_offset':pos,'size':len(d),'head32':d[:32].hex(),'tail32':d[-32:].hex()})
  if r['flags']!=3:continue
  # Reversible byte-order encodings sometimes masquerade as opaque payloads.
  for width in [2,4,8,16]:
   transformed=b''.join(d[i:i+width][::-1] for i in range(0,len(d),width))
   if hashlib.sha256(transformed).hexdigest()==digest:out['simple_transform_digest_matches'].append([name,r['name'],'byteswap',width])
  if len(d)<=65536:
   for key in range(256):
    trans=bytes.maketrans(bytes(range(256)),bytes(x^key for x in range(256)))
    if hashlib.sha256(d.translate(trans)).hexdigest()==digest:out['simple_transform_digest_matches'].append([name,r['name'],'xor8',key])
# Compare equal-digest payloads within/across versions, especially identical defaults.
entries=[]
for name,rows in meta.items():
 for r in rows:
  if r['flags']==3:entries.append((name,r))
for i,(na,a) in enumerate(entries):
 for nb,b in entries[i+1:]:
  if a['stored_sha256']!=b['stored_sha256'] or a['size']!=b['size']:continue
  da=blobs[na][512+a['offset']:512+a['offset']+a['size']];db=blobs[nb][512+b['offset']:512+b['offset']+b['size']]
  # first 64KiB sufficient for a simple reused-mask test; not a cryptographic proof
  xor=bytes(x^y for x,y in zip(da[:65536],db[:65536]));periods=[p for p in [1,2,4,8,16,32,64,128,256] if len(xor)>p and xor[p:]==xor[:-p]]
  out['equal_digest_pairs'].append({'a':na+':'+a['name'],'b':nb+':'+b['name'],'size':a['size'],'payload_equal':da==db,'aux_equal':a['aux16']==b['aux16'],'xor_sample_entropy':H(xor),'xor_short_periods':periods})
# Collect genuinely long strings from protected payloads; min 12 greatly reduces chance fragments.
import re
for name,rows in meta.items():
 for r in rows:
  if r['flags']!=3:continue
  d=blobs[name][512+r['offset']:512+r['offset']+r['size']]
  for m in re.finditer(rb'[\x20-\x7e]{12,}',d):
   out['readable_strings'].append({'file':name,'partition':r['name'],'file_offset':512+r['offset']+m.start(),'text':m.group().decode('ascii')})
(O/'payload_probe.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print('aux matches',[(x['file'],x['partition'],x['matches']) for x in out['aux_tests'] if x['matches']]);print('simple transform matches',out['simple_transform_digest_matches']);print('equal digest pairs',len(out['equal_digest_pairs']));print('same data pairs',[x for x in out['equal_digest_pairs'] if x['payload_equal']]);print('short XOR period pairs',[x for x in out['equal_digest_pairs'] if x['xor_short_periods']]);print('long string count',len(out['readable_strings']));print('equal pairs XOR entropy range',min(x['xor_sample_entropy'] for x in out['equal_digest_pairs']),max(x['xor_sample_entropy'] for x in out['equal_digest_pairs']))
