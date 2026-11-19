from pathlib import Path
import urllib.request,hashlib,json,re,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parent;O=R/'analysis'/'remote_menu';O.mkdir(exist_ok=True)
commit='985977636202bdeff5acaea82444c914834b1e1f'
base='https://raw.githubusercontent.com/sapoepsilon/lumix-remote/'+commit+'/'
paths=['evidence/real-s5/s5_allmenu.xml','evidence/real-s5/s5_curmenu.xml','emulator/data/dc-s5/capability.xml','emulator/data/dc-s5/ddd.xml']
result={'source_commit':commit,'files':[],'matches':[]}
pattern=re.compile(r'v.?log|lut|gamma|photo.?style|cinelike|709|assist|service|debug|firmware',re.I)
for remote in paths:
 data=urllib.request.urlopen(base+remote,timeout=40).read();p=O/Path(remote).name
 if p.exists():raise RuntimeError('Will not overwrite existing file: '+str(p))
 p.write_bytes(data);root=ET.fromstring(data)
 result['files'].append({'url':base+remote,'local':p.name,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'root_tag':root.tag})
 for node in root.iter():
  # attribute / direct text match only to avoid matching all ancestor trees
  text=' '.join([node.tag]+[str(k)+'='+str(v) for k,v in node.attrib.items()]+[(node.text or '').strip()])
  if pattern.search(text):
   result['matches'].append({'file':p.name,'tag':node.tag,'attributes':node.attrib,'text':(node.text or '').strip(),'subtree':ET.tostring(node,encoding='unicode')[:5000]})
(O/'menu_findings.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('FILES',json.dumps(result['files'],indent=2));print('MATCHES',len(result['matches']))
for m in result['matches']:print(m['file'],m['tag'],m['attributes'],m['text'])
