"""Download selected official source files for static review only; never extract or execute archive code."""
from pathlib import Path
import urllib.request,tarfile,hashlib,json
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'analysis'/'official_kernel_review';OUT.mkdir(exist_ok=True)
URL='https://ospo.panasonic.com/oss/source/dsc/DC-FZ1K2/linux-3.18.18.tar.gz'
exact=['net/ipv4/udp.c','net/ipv6/udp.c','net/core/datagram.c','net/bluetooth/l2cap_core.c','drivers/char/mem.c']
manifest={'url':URL,'scope':'official shared source listing includes DC-S5; not proof of running S5 v2.9 binary/config','files':[],'candidate_paths':[],'complete_archive':False}
try:
 with urllib.request.urlopen(URL,timeout=60) as response:
  manifest['http_headers']={k:response.headers.get(k) for k in ['Content-Length','Last-Modified','ETag']}
  with tarfile.open(fileobj=response,mode='r|gz') as archive:
   for member in archive:
    name=member.name.replace('\\','/')
    select=next((x for x in exact if name.endswith('/'+x) or name==x),None)
    isconfig='/arch/arm/configs/' in '/'+name and ('pvc' in name.lower() or 'milbeaut' in name.lower())
    isdts='/arch/arm/boot/dts/' in '/'+name and ('pvc02' in name.lower() or 'milbeaut' in name.lower())
    if ('crypto' in name.lower() or 'cipher' in name.lower() or 'ipc' in name.lower()) and any(t in name.lower() for t in ['milbeaut','pvc','socionext']):manifest['candidate_paths'].append(name)
    if not(select or isconfig or isdts):continue
    if not member.isfile() or member.size>4*1024*1024:continue
    # Output path is based solely on validated suffix or filename under a known prefix.
    label=select.replace('/','__') if select else Path(name).name
    dest=OUT/label
    if dest.exists():raise RuntimeError('Refusing to overwrite existing source: '+str(dest))
    stream=archive.extractfile(member)
    if stream is None:continue
    data=stream.read()
    if len(data)!=member.size:raise RuntimeError('Truncated selected member')
    dest.write_bytes(data)
    manifest['files'].append({'archive_path':name,'local_file':label,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    print('SAVED',label,len(data),flush=True)
   manifest['complete_archive']=True
except Exception as exc:
 manifest['error']=repr(exc);print('ERROR',repr(exc),flush=True)
finally:
 p=OUT/'source_manifest.json'
 if p.exists():raise RuntimeError('Refusing to overwrite manifest')
 p.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('FILES',len(manifest['files']),'full_stream_completed',manifest['complete_archive'],flush=True)
if 'error' in manifest:raise SystemExit(1)
