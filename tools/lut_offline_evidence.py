"""Offline-only evidence checks. No sockets, USB, process execution or firmware writes.
Config schema is narrowly based on the documented S5 0x9421 export, not a universal parser.
Synthetic self-tests validate this tool, NOT a camera LUT pipeline or a usable patch.
"""
from pathlib import Path
import argparse, struct, hashlib, json, tempfile

def sha(b):return hashlib.sha256(b).hexdigest()

def parse_config(b):
    if len(b)<69:raise ValueError('Config too short')
    tag,outer,inner=struct.unpack_from('<III',b)
    if tag!=0x080000a2:raise ValueError('Unsupported config tag; no schema guessing')
    if outer!=len(b)-8 or inner!=len(b)-12:raise ValueError('Config length mismatch')
    if b[-5:-1]!=b'\xff\xff\x00\x00':raise ValueError('Unknown terminator; refuse speculative parse')
    # Last byte preserved, not assumed to be a checksum.
    end=len(b)-5;pos=64;rows=[];occ={}
    while pos<end:
        if end-pos<6:raise ValueError('Truncated record header')
        rid,n,typ=struct.unpack_from('<HHH',b,pos)
        if n<6 or pos+n>end:raise ValueError('Invalid record length at '+hex(pos))
        key=(rid,typ);index=occ.get(key,0);occ[key]=index+1
        rows.append({'key':(rid,typ,index),'record_offset':pos,'payload_offset':pos+6,'data':b[pos+6:pos+n]})
        pos+=n
    if pos!=end:raise ValueError('Record alignment mismatch')
    return rows

def config_diff(blobs):
    parsed=[parse_config(b) for b in blobs]
    # Fail on changed record order/identity rather than compare unrelated bytes.
    keys=[[r['key'] for r in rows] for rows in parsed]
    if any(k!=keys[0] for k in keys[1:]):raise ValueError('Record identities/order changed; manual alignment required')
    result=[]
    for rows in zip(*parsed):
        values=[r['data'] for r in rows]
        if all(v==values[0] for v in values[1:]):continue
        a,b=values[:2];rec=rows[0]
        repeatable=len(values)==4 and values[0]==values[2] and values[1]==values[3] and a!=b
        bit_deltas=[]
        if len(a)==len(b):
            bit_deltas=[{'payload_byte':i,'xor_mask':f'0x{x^y:02x}'} for i,(x,y) in enumerate(zip(a,b)) if x!=y]
        result.append({'record_id':f'0x{rec["key"][0]:04x}','type':rec['key'][1],'occurrence':rec['key'][2],
                       'file_offsets':[r['payload_offset'] for r in rows],'values_hex':[v.hex() for v in values],
                       'bit_deltas':bit_deltas,'repeatable_ABAB':repeatable,
                       'semantic_status':'state-correlated only; not proof of LUT identity, executable xref or encoder consumption'})
    return {'input_sha256':[sha(b) for b in blobs],'record_count':len(parsed[0]),'changed_records':result,
            'limitations':'Metadata/header/trailer changes excluded, not explained. No device action. ABAB requires controlled same-mode captures and a sham control for stronger attribution.'}

def ptp_containers(blob,direction):
    pos=0;rows=[]
    allowed={'host-to-camera':{1,2},'camera-to-host':{2,3,4}}[direction]
    while pos<len(blob):
        if len(blob)-pos<12:raise ValueError('Truncated PTP header')
        n,typ,code,tid=struct.unpack_from('<IHHI',blob,pos)
        if n<12 or n>16*1024*1024 or pos+n>len(blob):raise ValueError('Invalid/truncated container length at '+hex(pos))
        if typ not in allowed:raise ValueError('Container type/direction mismatch at '+hex(pos))
        data=blob[pos+12:pos+n];params=None
        if typ in (1,3,4):
            if len(data)%4 or len(data)>20:raise ValueError('Invalid standard PTP parameter count/alignment')
            params=[f'0x{x:08x}' for x in struct.unpack('<'+'I'*(len(data)//4),data)]
        rows.append({'stream_offset':pos,'length':n,'type':typ,'code':f'0x{code:04x}','transaction_id':tid,
                     'parameters':params,'payload_sha256':sha(data),'scope':'transport container only; no camera-memory or LUT semantics inferred'})
        pos+=n
    return rows

def inventory(root):
    files=sorted(p for p in root.rglob('*') if p.is_file())
    # Ignore output from this tool itself to avoid reporting its own audit as raw evidence.
    raws=[p for p in files if p.suffix.lower() in {'.pcap','.pcapng','.usbpcap','.elf','.axf','.idb','.i64','.gpr','.gz','.xz'}]
    config=[p for p in files if p.suffix.lower()=='.bin' and any(k in p.name.lower() for k in ('config','camsetting','9421'))]
    g100=[p for p in files if p.suffix.lower()=='.bin' and p.name.lower().startswith('g100')]
    return {'workspace':str(root),'file_count':len(files),'raw_trace_or_executable_or_archive_candidates':[str(p.relative_to(root)) for p in raws],
            'config_binary_candidates':[str(p.relative_to(root)) for p in config],'g100_image_candidates':[str(p.relative_to(root)) for p in g100],
            'note':'Filename inventory, not a proof of file contents or exhaustive capture detection. Markdown citations and repository tree listings are not the cited raw artifacts.'}

def self_test():
    def config(value,extra=b''):
        rec=struct.pack('<HHH',0x1234,7,1)+bytes([value])+extra
        b=bytearray(64)+rec+b'\xff\xff\x00\x00\xbd'
        struct.pack_into('<III',b,0,0x080000a2,len(b)-8,len(b)-12)
        return bytes(b)
    a,b=config(0),config(1)
    d=config_diff([a,b,a,b]);assert len(d['changed_records'])==1 and d['changed_records'][0]['repeatable_ABAB']
    assert d['changed_records'][0]['file_offsets']==[70]*4
    assert not config_diff([a,b,b,a])['changed_records'][0]['repeatable_ABAB']
    bad=bytearray(a);struct.pack_into('<H',bad,66,0xffff)
    for operation in [lambda:parse_config(bytes(bad)),lambda:parse_config(a[:-1]),lambda:parse_config(bytes(80))]:
        try:operation()
        except ValueError:pass
        else:raise AssertionError('Malformed config accepted')
    cmd=struct.pack('<IHHII',16,1,0x9421,7,0x080000a2)
    assert ptp_containers(cmd,'host-to-camera')[0]['parameters']==['0x080000a2']
    rsp=struct.pack('<IHHI',12,3,0x2001,7);assert ptp_containers(rsp,'camera-to-host')[0]['code']=='0x2001'
    for operation in [lambda:ptp_containers(cmd[:-1],'host-to-camera'),lambda:ptp_containers(cmd,'camera-to-host'),lambda:ptp_containers(struct.pack('<IHHI',11,1,0x9421,7),'host-to-camera')]:
        try:operation()
        except ValueError:pass
        else:raise AssertionError('Malformed PTP accepted')
    return {'self_test':'PASS','synthetic_only':True,'network_or_camera_used':False,
            'checks':['ABAB repeatability','nonrepeatable control','record-relative vs file offsets','config lengths/records/tag','PTP length/direction/parameters'],
            'does_not_validate':['camera image pipeline','instruction address','hook safety','LUT recording functionality']}

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='mode',required=True)
    sub.add_parser('self-test')
    q=sub.add_parser('inventory');q.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    q=sub.add_parser('config-diff');q.add_argument('--a',required=True,type=Path);q.add_argument('--b',required=True,type=Path);q.add_argument('--a2',type=Path);q.add_argument('--b2',type=Path)
    q=sub.add_parser('ptp-summary');q.add_argument('--input',required=True,type=Path);q.add_argument('--direction',required=True,choices=['host-to-camera','camera-to-host'])
    args=p.parse_args()
    if args.mode=='self-test':result=self_test()
    elif args.mode=='inventory':result=inventory(args.root)
    elif args.mode=='config-diff':
        if bool(args.a2)!=bool(args.b2):p.error('Supply both --a2 and --b2, or neither')
        paths=[args.a,args.b]+([args.a2,args.b2] if args.a2 else [])
        result=config_diff([x.read_bytes() for x in paths])
    else:result={'input_sha256':sha(args.input.read_bytes()),'containers':ptp_containers(args.input.read_bytes(),args.direction),'note':'Input must be a pre-extracted contiguous USB PTP container stream of one direction, NOT a PCAP, PTP/IP or raw URB stream. No commands sent; no session or causal inference from separate direction streams.'}
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
