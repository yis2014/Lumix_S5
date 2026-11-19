"""Minimal DC-S5 menu evidence collector. Does not authenticate or change settings.
Run --self-test for an offline test. Network collection requires --host and --collect.
Existing official-app session may be required. Stop on camera errors; do not auto-retry.
"""
from pathlib import Path
import argparse,ipaddress,urllib.request,urllib.error,xml.etree.ElementTree as ET,json,hashlib,datetime
QUERIES=(('state','mode=getstate'),('capability','mode=getinfo&type=capability'),('allmenu','mode=getinfo&type=allmenu'),('curmenu','mode=getinfo&type=curmenu'))
LIMIT=2*1024*1024

def local_host(host):
 addr=ipaddress.IPv4Address(host)
 # Explicit LAN ranges; do not permit public hosts, DNS names or URL injection.
 if not any(addr in ipaddress.IPv4Network(net) for net in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
  raise ValueError('Only explicit private LAN IPv4 addresses are allowed')
 return str(addr)

def parse_response(data):
 if len(data)>LIMIT:raise ValueError('Response too large')
 if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('DTD/entity declarations rejected')
 root=ET.fromstring(data)
 result=root.findtext('result')
 return {'root':root.tag,'result':result,'success':result=='ok'}

class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise ValueError('Redirect rejected')

def collect(host,out,opener):
 host=local_host(host);out.mkdir(parents=True,exist_ok=False);records=[]
 for label,query in QUERIES:
  url='http://'+host+'/cam.cgi?'+query
  req=urllib.request.Request(url,method='GET',headers={'User-Agent':'S5-ReadOnly-Evidence/1.0','Connection':'close'})
  try:
   with opener.open(req,timeout=8) as response:
    data=response.read(LIMIT+1)
   parsed=parse_response(data)
   path=out/(label+'.xml');path.write_bytes(data)
   records.append({'query':query,'file':path.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),**parsed})
   if not parsed['success']:break
  except Exception as exc:
   records.append({'query':query,'error':str(exc)});break
 (out/'manifest.json').write_text(json.dumps({'host':host,'note':'GET queries only; no authentication/session/control/settings/stream commands. No automatic retries. Camera-side effects cannot be guaranteed absent.','records':records},indent=2),encoding='utf-8')
 return records

def self_test():
 import tempfile
 seen=[]
 class Reply:
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def read(self,n):return b'<camrply><result>ok</result></camrply>'
 class Fake:
  def open(self,req,timeout):seen.append((req.get_method(),req.full_url));return Reply()
 with tempfile.TemporaryDirectory() as temp:
  rows=collect('192.168.54.1',Path(temp)/'capture',Fake())
 assert len(rows)==4 and all(m=='GET' for m,u in seen)
 assert [u.split('?',1)[1] for m,u in seen]==[q for _,q in QUERIES]
 for bad in ('8.8.8.8','127.0.0.1','example.com','192.168.1.1/path'):
  try:local_host(bad)
  except ValueError:pass
  else:raise AssertionError(bad)
 assert not parse_response(b'<camrply><result>err_busy</result></camrply>')['success']
 print('PASS: offline mocked four GET requests, local-address guard, camera-error recognition; no network used')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host');p.add_argument('--collect',action='store_true');p.add_argument('--self-test',action='store_true');args=p.parse_args()
 if args.self_test:self_test();return
 if not(args.host and args.collect):p.error('Network collection requires both --host PRIVATE_IP and --collect. No requests sent.')
 out=Path(__file__).resolve().parent/'analysis'/('camera_capture_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
 records=collect(args.host,out,opener);print(json.dumps(records,indent=2));print('Saved:',out)

if __name__=='__main__':main()
