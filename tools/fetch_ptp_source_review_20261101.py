"""Acquire pinned public libgphoto2 source for offline Panasonic interface review.
No camera access and no downloaded source execution/compilation.
"""
from pathlib import Path
import urllib.request,json,hashlib
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis/eeprom_keyhunt_20261101/ptp_source_review';OUT.mkdir(exist_ok=True)
REPO='gphoto/libgphoto2'
HEAD='https://api.github.com/repos/'+REPO+'/commits/master'
headers={'User-Agent':'Firmware-source-review','Accept':'application/vnd.github+json'}
with urllib.request.urlopen(urllib.request.Request(HEAD,headers=headers),timeout=30) as r:commit=json.loads(r.read(1024*1024))
sha=commit['sha'];assert len(sha)==40
paths=['camlibs/ptp2/ptp.h','camlibs/ptp2/ptp.c','camlibs/ptp2/config.c','camlibs/ptp2/library.c','camlibs/ptp2/ptp-pack.c']
rows=[];total=0
for path in paths:
    url='https://raw.githubusercontent.com/'+REPO+'/'+sha+'/'+path
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Firmware-source-review'}),timeout=45) as r:
        data=r.read(4*1024*1024+1);assert len(data)<=4*1024*1024
    total+=len(data);assert total<=12*1024*1024
    p=OUT/Path(path).name
    if p.exists():assert p.read_bytes()==data
    else:
        with p.open('xb') as f:f.write(data)
    row=dict(repo=REPO,commit=sha,path=path,url=url,file=str(p.relative_to(ROOT)),size=len(data),sha256=hashlib.sha256(data).hexdigest())
    rows.append(row);print('SAVED',path,len(data),flush=True)
result=dict(commit=sha,commit_url=commit['html_url'],sources=rows,downloaded_code_executed=False,camera_access=False)
(OUT/'source_manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
