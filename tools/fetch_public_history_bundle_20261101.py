"""Fetch one public Git bundle as inert evidence, verifying Git blob identity.
No checkout, code execution, forms, license acceptance, or device access.
"""
from pathlib import Path
import urllib.request,urllib.parse,hashlib,json,re,time
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis/eeprom_keyhunt_20261101/public_history'
OUT.mkdir(parents=True,exist_ok=True)
REL='14_总包审计与新方向_20261014/10_仓库补丁/S5-wireless-monitor_v1.1.bundle'
URL='https://raw.githubusercontent.com/williamwu1234/S5-reverse-engineering/2eec64d099dd895db33f4e34c2d856ffc1b7c3d5/'+urllib.parse.quote(REL,safe='/')
SIZE=60898024;GIT_BLOB='31bb1b34aeb862bfb2e2743364d89798a80a2305'
P=OUT/'S5-wireless-monitor_v1.1.bundle'
started=time.monotonic();requests=[]
if P.exists():
    data=P.read_bytes()
else:
    cache=OUT/'download_parts';cache.mkdir(exist_ok=True)
    pieces=[];position=0;request_count=0
    while position<SIZE:
        part=cache/('part_%09d.bin'%position)
        if part.exists():
            chunk=part.read_bytes()
            if not 0<len(chunk)<=min(1024*1024,SIZE-position):raise RuntimeError('Invalid cached part')
            pieces.append(chunk);position+=len(chunk);continue
        end=min(position+1024*1024,SIZE)-1
        request_count+=1
        if request_count>256:raise RuntimeError('Bounded request count exhausted')
        req=urllib.request.Request(URL,headers={'Range':f'bytes={position}-{end}','User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req,timeout=60) as response:
            status=response.status;cr=response.headers.get('Content-Range')
            if status==200:
                if position!=0:raise RuntimeError('Unexpected full response to nonzero range')
                chunk=response.read(SIZE+1)
                if len(chunk)!=SIZE:raise RuntimeError('Incomplete/unexpected full bundle')
                pieces=[chunk];position=SIZE
            elif status==206:
                m=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',cr or '')
                if not m or int(m[1])!=position or int(m[3])!=SIZE or int(m[2])>end:raise RuntimeError('Unexpected content range')
                chunk=response.read(end-position+2)
                # An interrupted HTTP range may contain a valid prefix. Retain
                # only received bytes, resume at the next byte, and require the
                # entire known Git blob hash before treating it as evidence.
                if not 0<len(chunk)<=int(m[2])-position+1:raise RuntimeError('Invalid/empty range')
                with part.open('xb') as f:f.write(chunk)
                pieces.append(chunk);position+=len(chunk)
            else:raise RuntimeError('Unexpected HTTP status')
        requests.append(dict(status=status,content_range=cr,received_bytes=len(chunk),downloaded_total=position))
        print('DOWNLOADED',position,'/',SIZE,flush=True)
    data=b''.join(pieces)
assert len(data)==SIZE
blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
assert blob==GIT_BLOB,(blob,GIT_BLOB)
if not P.exists():
    with P.open('xb') as f:f.write(data)
assert P.read_bytes()==data
result=dict(url=URL,source_commit='2eec64d099dd895db33f4e34c2d856ffc1b7c3d5',path=REL,
    bytes=len(data),git_blob_sha1=blob,sha256=hashlib.sha256(data).hexdigest(),requests=requests,
    elapsed_seconds=time.monotonic()-started,executed_or_checked_out=False)
(OUT/'bundle_source.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
