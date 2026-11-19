from pathlib import Path
import urllib.request,urllib.parse,json,hashlib
R=Path(__file__).resolve().parent;O=R/'analysis'/'william_review';O.mkdir(exist_ok=True)
repo='williamwu1234/S5-reverse-engineering';commit='660247dc05e68d0645d96984437a3dade0b2c076'
req=urllib.request.Request(f'https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1',headers={'User-Agent':'S5-Offline-Review'})
tree=json.load(urllib.request.urlopen(req,timeout=40));(O/'tree.json').write_text(json.dumps(tree,ensure_ascii=False,indent=2),encoding='utf-8')
paths=['README.md','01_唯一权威调用文档.md','06_证据索引.md','13_新疑点与新方向_20261016.md','11_密码学_正确偏移密钥搜索_20261016/结论.md','11_密码学_正确偏移密钥搜索_20261016/upd_table.py','11_密码学_正确偏移密钥搜索_20261016/exp5_real_key_search_corrected.py','11_密码学_正确偏移密钥搜索_20261016/out/exp5_real_key_search.json']
manifest=[]
for remote in paths:
 url=f'https://raw.githubusercontent.com/{repo}/{commit}/'+urllib.parse.quote(remote,safe='/')
 data=urllib.request.urlopen(url,timeout=40).read();p=O/remote;p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():raise RuntimeError('Existing file '+str(p))
 p.write_bytes(data);manifest.append({'path':remote,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'url':url})
(O/'sources.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('Downloaded documents only; no downloaded code executed.')
for x in tree['tree']:
 if any(k.lower() in x['path'].lower() for k in ['k32','crypto','plain','decrypt','kernel','linux','uart','firmware_crypto']):print(x['path'],x.get('size',''))
