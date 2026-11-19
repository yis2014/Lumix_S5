"""Offline parser for an observed Panasonic 0x9402 property-group DATA payload.
No USB/network or device actions. Does not assign field semantics from numeric tags.
"""
from pathlib import Path
import struct,hashlib,json,argparse

def parse(data):
    pos=0;out=[]
    while pos<len(data):
        if len(data)-pos<8:raise ValueError('Trailing/incomplete TLV header')
        tag,n=struct.unpack_from('<II',data,pos)
        if n>len(data)-pos-8:raise ValueError('TLV length beyond payload')
        v=data[pos+8:pos+8+n]
        out.append({'offset':pos,'tag':f'0x{tag:08x}','bytes':n,'value_hex':v.hex(),'integer_le':int.from_bytes(v,'little') if n in (1,2,4,8) else None})
        pos+=8+n
    return out

def test():
    a=struct.pack('<IIH',0x02000011,2,40)+struct.pack('<III',0x0200001d,4,0xffffffff)
    p=parse(a);assert len(p)==2 and p[0]['integer_le']==40 and p[1]['integer_le']==0xffffffff
    for bad in (a[:-1],b'\x00',struct.pack('<II',1,10)):
        try:parse(bad)
        except ValueError:pass
        else:raise AssertionError('Accepted invalid payload')
    return 'PASS'

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('input',type=Path);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    data=args.input.read_bytes();r={'self_test':test(),'input':str(args.input),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'scope':'observed 9402 group TLV framing; field meanings unassigned','records':parse(data)}
    with args.output.open('x',encoding='utf-8') as f:json.dump(r,f,ensure_ascii=False,indent=2)
    print(json.dumps(r,ensure_ascii=False,indent=2))
