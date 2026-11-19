"""Offline read-only Panasonic UPD container comparison. Never executes or modifies image bytes.
A directory target is NOT treated as a virtual address; no encryption algorithm is inferred.
"""
from pathlib import Path
import struct,hashlib,zlib,json,csv,collections,math
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis'/'still_lut_port'
FILES=['S5___V28.bin','S5___V29.bin','S5m2_V37.bin']
def digest(b):return hashlib.sha256(b).hexdigest()
def parse(b,name):
    if len(b)<0x300 or b[:4]!=b'UPD\0':raise ValueError('Not expected UPD container')
    count=struct.unpack_from('<I',b,0x2e8)[0]
    if not 1<=count<=256 or 0x2ec+count*92>len(b):raise ValueError('Invalid table bounds/count')
    rows=[];occurrences=collections.Counter()
    for i in range(count):
        p=0x2ec+i*92;n=b[p:p+12].split(b'\0')[0].decode('ascii')
        if not n or any(ord(x)<32 or ord(x)>126 for x in n):raise ValueError('Invalid entry name')
        occurrence=occurrences[n];occurrences[n]+=1;off,size,target,flags=struct.unpack_from('<4I',b,p+12);start=off+0x200;end=start+size
        if start<0x2ec+count*92 or end>len(b):raise ValueError('Entry outside payload bounds')
        data=memoryview(b)[start:end];actual=hashlib.sha256(data).hexdigest();expected=b[p+28:p+60].hex()
        row={'index':i,'name':n,'occurrence':occurrence,'entry_file_offset':p,'stored_offset':off,'file_offset':start,'size':size,'directory_target_unmapped':target,'flags':flags,'directory_digest32':expected,'raw_sha256':actual,'raw_matches_directory_digest':actual==expected,'aux16':b[p+60:p+76].hex(),'trailer16':b[p+76:p+92].hex(),'head32_hex':bytes(data[:32]).hex()}
        if n in ('program','zimage','rootfs1','rootfs2') and size:
            c=collections.Counter(data);row['byte_entropy']=-sum((v/size)*math.log2(v/size) for v in c.values());row['entropy_is_not_an_encryption_or_ISA_proof']=True
        rows.append(row)
    spans=sorted((r['file_offset'],r['file_offset']+r['size'],r['name']) for r in rows if r['size'])
    for a,c in zip(spans,spans[1:]):
        if a[1]>c[0]:raise ValueError('Overlapping entries')
    crc=struct.unpack_from('<I',b,0x40)[0];calculated=zlib.crc32(memoryview(b)[512:])
    return {'file':name,'bytes':len(b),'sha256':digest(b),'container_model':b[12:28].split(b'\0')[0].decode('ascii'),'outer_crc32':f'0x{crc:08x}','calculated_body_crc32':f'0x{calculated:08x}','crc_matches':crc==calculated,'directory_count':count,'directory_stride':92,'table_file_offset':0x2ec,'physical_data_base':512,'max_payload_end':max((r['file_offset']+r['size'] for r in rows),default=0),'payloads_end_at_EOF':max(r['file_offset']+r['size'] for r in rows)==len(b),'flags_counts':dict(collections.Counter(r['flags'] for r in rows)),'header_0x220_0x260':b[0x220:0x260].hex(),'header_0x220_0x260_semantics':'unknown; not asserted to be key/signature/nonce','entries':rows}

def selftest():
    b=bytearray(4096);b[:4]=b'UPD\0';b[12:17]=b'TEST0';struct.pack_into('<I',b,0x2e8,1);p=0x2ec;b[p:p+4]=b'boot';struct.pack_into('<4I',b,p+12,0x800,16,0x42,2);b[0xa00:0xa10]=bytes(range(16));b[p+28:p+60]=hashlib.sha256(b[0xa00:0xa10]).digest();struct.pack_into('<I',b,0x40,zlib.crc32(b[512:]));r=parse(bytes(b),'synthetic');assert r['entries'][0]['file_offset']==0xa00 and r['entries'][0]['directory_target_unmapped']==0x42 and r['crc_matches'] and r['entries'][0]['raw_matches_directory_digest']
    bad=bytearray(b);struct.pack_into('<I',bad,0x2e8,10000)
    try:parse(bytes(bad),'invalid')
    except ValueError:pass
    else:raise AssertionError('Accepted corrupt count')
    repeated=bytearray(b);struct.pack_into('<I',repeated,0x2e8,2);repeated[0x2ec+92:0x2ec+184]=repeated[0x2ec:0x2ec+92];struct.pack_into('<I',repeated,0x2ec+92+12,0x900);r=parse(bytes(repeated),'duplicate_name');assert [x['occurrence'] for x in r['entries']]==[0,1]
    return 'PASS'

def compare(a,b):
    aa={f"{x['name']}#{x['occurrence']}":x for x in a['entries']};bb={f"{x['name']}#{x['occurrence']}":x for x in b['entries']};rows=[]
    for n in sorted(aa.keys()&bb.keys()):
        x,y=aa[n],bb[n];rows.append({'name':x['name'],'occurrence':x['occurrence'],'match_key':n,'a_file_offset':x['file_offset'],'b_file_offset':y['file_offset'],'a_size':x['size'],'b_size':y['size'],'a_directory_target':x['directory_target_unmapped'],'b_directory_target':y['directory_target_unmapped'],'size_equal':x['size']==y['size'],'directory_digest_equal':x['directory_digest32']==y['directory_digest32'],'raw_payload_equal':x['raw_sha256']==y['raw_sha256'],'flags_equal':x['flags']==y['flags'],'aux16_equal':x['aux16']==y['aux16'],'trailer16_equal':x['trailer16']==y['trailer16']})
    return {'a':a['file'],'b':b['file'],'a_model':a['container_model'],'b_model':b['container_model'],'only_a':sorted(aa.keys()-bb.keys()),'only_b':sorted(bb.keys()-aa.keys()),'matched_name_count':len(rows),'equal_directory_digest_names':[r['name'] for r in rows if r['directory_digest_equal']],'equal_raw_payload_names':[r['name'] for r in rows if r['raw_payload_equal']],'entries':rows,'limitations':'Same name or equal directory digest is not function homology. Targets unmapped. No authenticity/signature or ISA established.'}

def main():
    OUT.mkdir(exist_ok=True);report={'scope':'offline container comparison only','self_test':selftest(),'inputs':[],'comparisons':[],'known_resource_checks':[]}
    for file in FILES:
        r=parse((ROOT/file).read_bytes(),file);report['inputs'].append(r);print(file,r['bytes'],r['container_model'],'CRC',r['crc_matches'],'entries',r['directory_count'],flush=True)
    report['comparisons']=[compare(report['inputs'][0],report['inputs'][1]),compare(report['inputs'][1],report['inputs'][2])]
    for sample in sorted((ROOT/'analysis'/'william_review'/'plaintext_samples').glob('*.bin')):
        data=sample.read_bytes();h=digest(data)
        matches=[{'image':r['file'],'entry':e['name'],'raw_payload_equal':e['raw_sha256']==h} for r in report['inputs'] for e in r['entries'] if e['size']==len(data) and e['directory_digest32']==h]
        report['known_resource_checks'].append({'sample':str(sample.relative_to(ROOT)),'bytes':len(data),'sha256':h,'directory_matches':matches,'scope':'resource identity check, not executable plaintext or general decryption'})
    dest=OUT/'container_comparison.json'
    with dest.open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    dest=OUT/'s5_v29_vs_s5m2_v37.csv'
    with dest.open('x',encoding='utf-8-sig',newline='') as f:
        rows=report['comparisons'][1]['entries'];w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    for r in report['comparisons']:print(r['a'],'->',r['b'],'common',r['matched_name_count'],'only_b',r['only_b'],'equal_dir_digest',r['equal_directory_digest_names'],flush=True)
if __name__=='__main__':main()
