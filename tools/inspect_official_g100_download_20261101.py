"""Fetch public official HTML only. Does not submit forms, accept terms, run JS,
download firmware, or contact a camera. Preserves source to inspect exact links.
"""
from pathlib import Path
import urllib.request, re, json, hashlib
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis'/'eeprom_keyhunt_20261101'/'official_source'
OUT.mkdir(parents=True,exist_ok=True)
URLS={
    'g100_product.html':'https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/dl/g100_g110.html',
    'g100_download.html':'https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/dl/g100_dl.html'}
rows=[]
for filename,url in URLS.items():
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req,timeout=30) as r:
        data=r.read(2*1024*1024);final=r.url;status=r.status
    text=data.decode('utf-8',errors='replace')
    p=OUT/filename
    if p.exists():
        if p.read_bytes()!=data:raise ValueError('Prior source differs; retain separately')
    else:p.write_bytes(data)
    row=dict(url=url,final_url=final,status=status,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),
             links=re.findall(r'(?:href|src|action)\s*=\s*[\"\']([^\"\']+)',text,re.I),
             relevant_lines=[dict(line=i,text=line[:2000]) for i,line in enumerate(text.splitlines(),1)
                if re.search(r'zip|agree|license|iframe|\.js|download|accept',line,re.I)])
    rows.append(row)
    print(json.dumps(row,ensure_ascii=False),flush=True)
(OUT/'html_links.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
