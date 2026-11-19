"""Obtain the exact official G100 V1.3 sample after user approval of download.
Submits only the previously inspected MODEL/Accepted form; no device access.
Firmware is stored as inert evidence, never executed or flashed.
"""
from pathlib import Path
import urllib.request,urllib.parse,http.client,json,hashlib,zipfile,io,re,time
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis/eeprom_keyhunt_20261101/g100_official'
OUT.mkdir(parents=True,exist_ok=True)
FORM='https://av.jpn.support.panasonic.com/support/cgi-bin/global_cs/dsc/download_g.cgi'
REFERER='https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/dl/g100_dl.html'
EXPECTED=58933998
ZIP=OUT/'G100_V13.zip';BIN=OUT/'G100_V13.bin'
requests=[];started=time.monotonic()

def read_at_most(response,n):
    try:return response.read(n)
    except http.client.IncompleteRead as e:return e.partial

def main():
    if ZIP.exists():
        data=ZIP.read_bytes();final_url='previously_saved_official_sample'
    else:
        req=urllib.request.Request(FORM,data=urllib.parse.urlencode({'MODEL':'G100_V13.zip','submit':'Accepted'}).encode('ascii'),
            headers={'User-Agent':'Mozilla/5.0','Referer':REFERER,'Content-Type':'application/x-www-form-urlencoded'},method='POST')
        with urllib.request.urlopen(req,timeout=90) as response:
            final_url=response.url;status=response.status;headers=dict(response.headers.items())
            data=read_at_most(response,EXPECTED+1)
        requests.append(dict(method='POST',url=FORM,final_url=final_url,status=status,headers=headers,bytes_received=len(data)))
        if not data.startswith(b'PK\x03\x04'):
            with (OUT/'download_response.bin').open('xb') as f:f.write(data)
            (OUT/'download_response_metadata.json').write_text(json.dumps(requests,indent=2),encoding='utf-8')
            raise RuntimeError('Official form did not return ZIP; inspect response as inert text only')
        if len(data)>EXPECTED:raise RuntimeError('Unexpected package length')
        position=len(data);pieces=[data]
        while position<EXPECTED:
            end=min(position+1024*1024,EXPECTED)-1
            req=urllib.request.Request(final_url,headers={'User-Agent':'Mozilla/5.0','Referer':REFERER,'Range':f'bytes={position}-{end}'})
            with urllib.request.urlopen(req,timeout=60) as response:
                cr=response.headers.get('Content-Range');status=response.status
                m=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',cr or '')
                if status!=206 or not m or int(m[1])!=position or int(m[2])>end or int(m[3])!=EXPECTED:raise RuntimeError('Unexpected resume response')
                chunk=read_at_most(response,end-position+2)
            if not 0<len(chunk)<=int(m[2])-position+1:raise RuntimeError('Invalid resumed chunk')
            pieces.append(chunk);position+=len(chunk)
            requests.append(dict(method='GET',status=status,content_range=cr,bytes_received=len(chunk),total=position))
            print('RESUMED',position,'/',EXPECTED,flush=True)
        data=b''.join(pieces)
        assert len(data)==EXPECTED
        with ZIP.open('xb') as f:f.write(data)
    assert len(data)==EXPECTED
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        members=z.infolist()
        assert len(members)<=16 and sum(e.file_size for e in members)<=256*1024*1024
        assert all(not (e.flag_bits&1) for e in members)
        assert z.testzip() is None
        selected=[e for e in members if e.filename.replace('\\','/').split('/')[-1]=='G100_V13.bin']
        assert len(selected)==1
        binary=z.read(selected[0])
        listing=[dict(name=e.filename,bytes=e.file_size,compressed=e.compress_size,crc32=hex(e.CRC)) for e in members]
    if BIN.exists():assert BIN.read_bytes()==binary
    else:
        with BIN.open('xb') as f:f.write(binary)
    result=dict(official_product_page='https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/dl/g100_g110.html',
        user_approved_form_submission=True,form_url=FORM,form_fields={'MODEL':'G100_V13.zip','submit':'Accepted'},
        final_url=final_url,zip_bytes=len(data),zip_sha256=hashlib.sha256(data).hexdigest(),members=listing,
        bin_bytes=len(binary),bin_sha256=hashlib.sha256(binary).hexdigest(),bin_head128=binary[:128].hex(),
        zip_crc_validation=True,manufacturer_signature_validated=False,executed_or_flashed=False,
        requests=requests,elapsed_seconds=time.monotonic()-started)
    (OUT/'official_sample_source.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
