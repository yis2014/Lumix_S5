"""Fetch source dependencies only from official archive. No camera access, code execution or general extraction."""
from pathlib import Path
import urllib.request,tarfile,hashlib,json
R=Path(__file__).resolve().parent;O=R/'analysis'/'official_kernel_review';U='https://ospo.panasonic.com/oss/source/dsc/DC-FZ1K2/linux-3.18.18.tar.gz'
wanted={'include/linux/skbuff.h','include/net/udp.h','net/core/skbuff.c'};found=[]
report={'url':U,'scope':'selected official archive members only; intentional early stop does not validate whole archive CRC','members':found,'complete_required_set':False}
try:
 with urllib.request.urlopen(U,timeout=60) as response:
  report['headers']={k:response.headers.get(k) for k in ('ETag','Last-Modified','Content-Length')}
  with tarfile.open(fileobj=response,mode='r|gz') as archive:
   for m in archive:
    path=m.name.replace('\\','/');suffix=next((x for x in wanted if path.endswith('/'+x)),None)
    if suffix is None or not m.isfile():continue
    if m.size>4*1024*1024:raise ValueError('Unexpected member size')
    data=archive.extractfile(m).read()
    if len(data)!=m.size:raise ValueError('Truncated selected member')
    dest=O/suffix.replace('/','__')
    if dest.exists():raise RuntimeError('Refuse overwrite')
    dest.write_bytes(data);found.append({'archive_path':path,'file':dest.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()});wanted.remove(suffix)
    print('SAVED',dest.name,len(data),flush=True)
    if not wanted:report['complete_required_set']=True;break
except Exception as e:
 report['error']=repr(e);print('ERROR',repr(e),flush=True)
p=O/'candidate_A_dependency_sources.json'
if p.exists():raise RuntimeError('Refuse manifest overwrite')
p.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('Complete required set:',report['complete_required_set'],flush=True)
if not report['complete_required_set']:raise SystemExit(1)
