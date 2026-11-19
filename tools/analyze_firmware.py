from pathlib import Path
import hashlib, math, collections, re, json, struct
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis'; OUT.mkdir(exist_ok=True)
files=['S5___V28.bin','S5___V29.bin','400BV020.plf']
def entropy(b):
 c=collections.Counter(b); n=len(b)
 return -sum((v/n)*math.log2(v/n) for v in c.values()) if n else 0
results={}
for name in files:
 b=(ROOT/name).read_bytes()
 blocks=[{'offset':i,'length':len(b[i:i+65536]),'entropy':round(entropy(b[i:i+65536]),6)} for i in range(0,len(b),65536)]
 strings=[(m.start(),m.group().decode('ascii')) for m in re.finditer(rb'[\x20-\x7e]{6,}',b)]
 (OUT/(name+'.strings.txt')).write_text('\n'.join(f'{o:08X} {s}' for o,s in strings),encoding='utf-8')
 sigs={'ELF':b'\x7fELF','gzip':b'\x1f\x8b\x08','XZ':b'\xfd7zXZ\x00','ZIP':b'PK\x03\x04','uImage':b'\x27\x05\x19\x56','SquashFS':b'hsqs','UBI':b'UBI#','FDT':b'\xd0\x0d\xfe\xed','LZ4':b'\x04\x22\x4d\x18','ZSTD':b'\x28\xb5\x2f\xfd'}
 found={}
 for k,s in sigs.items():
  hits=[]; p=0
  while (p:=b.find(s,p))>=0:
   hits.append(p); p+=1
  if hits: found[k]=hits[:100]
 results[name]={'size':len(b),'sha256':hashlib.sha256(b).hexdigest(),'head256':b[:256].hex(' '),'tail256':b[-256:].hex(' '),'entropy':entropy(b),'ascii_strings_count':len(strings),'entropy_blocks':blocks,'magic_candidates_unvalidated':found,'most_common_bytes':collections.Counter(b).most_common(16)}
 print(name,json.dumps({k:v for k,v in results[name].items() if k not in ('entropy_blocks','head256','tail256')},ensure_ascii=False))
a=(ROOT/files[0]).read_bytes(); b=(ROOT/files[1]).read_bytes()
diff=[]
for i in range(0,len(a),65536):
 x=a[i:i+65536];y=b[i:i+65536]; n=sum(v!=w for v,w in zip(x,y))
 diff.append({'offset':i,'different_bytes':n,'length':len(x)})
first=next((i for i,(x,y) in enumerate(zip(a,b)) if x!=y),None)
last=next((len(a)-1-i for i,(x,y) in enumerate(zip(reversed(a),reversed(b))) if x!=y),None)
results['comparison']={'different_bytes':sum(d['different_bytes'] for d in diff),'first_difference':first,'last_difference':last,'blocks':diff}
(OUT/'firmware_summary.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print('DIFF',results['comparison']['different_bytes'],first,last)
for name in files:
 print('HEADER',name,results[name]['head256'])
 print('TAIL',name,results[name]['tail256'])
