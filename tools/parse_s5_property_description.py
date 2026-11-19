"""Offline bounded parser for the observed DC-S5 0x9108 PhotoStyle description tree.
Schema inferred from D1 and independently checked against D2 0x9402 values; not universal PTP.
No USB/network/device actions. Refuses unrecognized layout instead of guessing.
"""
from pathlib import Path
import struct,json,hashlib,argparse
from parse_panasonic_property import parse as parse_values

def need(ok,message):
    if not ok:raise ValueError(message)
def record(b,pos,limit):
    need(0<=pos<=limit<=len(b) and limit-pos>=8,'truncated TLV header')
    tag,n=struct.unpack_from('<II',b,pos);end=pos+8+n
    need(end<=limit,'TLV beyond containing range')
    return tag,b[pos+8:end],end

def description(b,values):
    known={int(x['tag'],16):x for x in values}
    rt,body,pos=record(b,0,len(b));need(rt==0x02000010 and len(body)==20,'unexpected root descriptor')
    meta=struct.unpack('<5I',body);need(meta[0]==20 and pos+meta[4]==len(b),'root span mismatch')
    fields=[]
    for index in range(meta[3]):
        start=pos;tag,head,pos=record(b,pos,len(b));need(len(head)==20,'unexpected child descriptor size')
        h=struct.unpack('<5I',head);need(h[0]==20 and h[3]==1,'expected one value record per child')
        end=pos+h[4];need(end<=len(b),'child range overflow')
        leaf,data,nextpos=record(b,pos,end);need(leaf==1 and nextpos==end,'unexpected value-record framing')
        need(tag in known,'description child missing from independent getter')
        width=known[tag]['bytes'];need(width in (2,4) and len(data)>=24+width+4,'value width/length unsupported')
        opaque=struct.unpack_from('<6I',data)
        # Standard PTP-compatible type codes: UINT16=4, UINT32=6; form=2 enumerated.
        # Checked against every independent getter width, not guessed from word[5].
        need(opaque[4]=={2:4,4:6}[width] and opaque[5]==2,'type/form disagrees with observed getter/schema')
        current=data[24:24+width];count=struct.unpack_from('<I',data,24+width)[0]
        array=28+width;need(count<=(len(data)-array)//width and array+count*width==len(data),'enumeration count/size mismatch')
        opts=[int.from_bytes(data[array+i*width:array+(i+1)*width],'little') for i in range(count)]
        fields.append({'tag':f'0x{tag:08x}','descriptor_offset':start,'descriptor_words_u32':list(h),'value_record_offset':pos,'opaque_value_metadata_u32':list(opaque),'width':width,'current_hex':current.hex(),'current_u32':int.from_bytes(current,'little'),'matches_independent_getter':current.hex()==known[tag]['value_hex'],'enumerated_values':opts})
        pos=end
    need(pos==len(b) and set(known)=={int(x['tag'],16) for x in fields},'unconsumed bytes or getter/descriptor tag mismatch')
    need(all(x['matches_independent_getter'] for x in fields),'description values differ from independent getter')
    return {'root_tag':hex(rt),'root_metadata_words':list(meta),'child_count':len(fields),'all_current_values_match_getter':True,'fields':fields}

def fixture():
    pairs=[(0x02000011,2,40,[0,2,40]),(0x0200001d,4,0xffffffff,[0xffffffff])];chunks=[];vals=[]
    for tag,w,cur,opts in pairs:
        payload=struct.pack('<6I',0,0x10001,0,1,{2:4,4:6}[w],2)+cur.to_bytes(w,'little')+struct.pack('<I',len(opts))+b''.join(x.to_bytes(w,'little') for x in opts)
        leaf=struct.pack('<II',1,len(payload))+payload;head=struct.pack('<II5I',tag,20,20,0x10001,0,1,len(leaf));chunks.append(head+leaf)
        vals.append({'tag':hex(tag),'bytes':w,'value_hex':cur.to_bytes(w,'little').hex()})
    tail=b''.join(chunks);return struct.pack('<II5I',0x02000010,20,20,0x10001,0,len(chunks),len(tail))+tail,vals

def selftest():
    b,vals=fixture();need(description(b,vals)['child_count']==2,'fixture')
    bad=bytearray(b);struct.pack_into('<I',bad,24,len(b)+999)
    for broken in (b[:-1],bytes(bad),b'\0'):
        try:description(broken,vals)
        except ValueError:pass
        else:raise AssertionError('accepted malformed fixture')
    return 'PASS: synthetic bounds/width fixtures; no camera fuzz'

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--description',type=Path,required=True);ap.add_argument('--values',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    b=args.description.read_bytes();v=args.values.read_bytes();r={'self_test':selftest(),'scope':'observed PhotoStyle description tree only; no other property queries','description_sha256':hashlib.sha256(b).hexdigest(),'getter_sha256':hashlib.sha256(v).hexdigest(),**description(b,parse_values(v))}
    first=next(x for x in r['fields'] if x['tag']=='0x02000011');r['PhotoStyle_first_field_summary']={'current':first['current_u32'],'advertised_values':first['enumerated_values'],'value_49_advertised':49 in first['enumerated_values'],'limitations':'Absence from this response is not proof of absent ISP capability or a hidden global command/property'}
    with args.output.open('x',encoding='utf-8') as f:json.dump(r,f,ensure_ascii=False,indent=2)
    print(json.dumps({'self_test':r['self_test'],'child_count':r['child_count'],'all_current_values_match_getter':r['all_current_values_match_getter'],'PhotoStyle_first_field_summary':r['PhotoStyle_first_field_summary']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
