"""Compare actual official G100 FDT bytes with new public BSP source.
No compiler or firmware execution. Do not infer S5 hardware from shared page.
"""
from pathlib import Path
import json,struct,hashlib
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'analysis/eeprom_keyhunt_20261101'
OUT=BASE/'official_oss_review/parent_review';OUT.mkdir(exist_ok=True)

def sha(b):return hashlib.sha256(b).hexdigest()
def parse_fdt(b):
    magic,total,off_struct,off_strings,off_reserve,version,lastcompatible,boot_cpu,size_strings,size_struct=struct.unpack_from('>10I',b,0)
    assert magic==0xd00dfeed and total<=len(b) and version==17
    strings=b[off_strings:off_strings+size_strings];pos=off_struct;end=off_struct+size_struct;stack=[];properties=[]
    while pos<end:
        token=struct.unpack_from('>I',b,pos)[0];pos+=4
        if token==1:
            e=b.index(0,pos,end);name=b[pos:e].decode('ascii');pos=(e+4)&~3;stack.append(name)
        elif token==2:
            assert stack;stack.pop()
        elif token==3:
            length,nameoff=struct.unpack_from('>2I',b,pos);pos+=8
            assert pos+length<=end and nameoff<len(strings)
            e=strings.index(0,nameoff);name=strings[nameoff:e].decode('ascii');value_offset=pos;value=b[pos:pos+length];pos=(pos+length+3)&~3
            row=dict(path='/'+'/'.join(s for s in stack if s),name=name,length=length,value_offset=value_offset,hex=value.hex())
            if value and value[-1]==0:
                try:
                    text=value.rstrip(b'\0').decode('ascii')
                    if all(c.isprintable() or c=='\0' for c in text):row['strings']=text.split('\0')
                except UnicodeDecodeError:pass
            if length%4==0:row['cells_BE']=list(struct.unpack('>'+str(length//4)+'I',value))
            properties.append(row)
        elif token==4:continue
        elif token==9:break
        else:raise ValueError('Invalid FDT token '+str(token))
    assert not stack
    return dict(total_size=total,section_size=len(b),version=version,boot_cpu=boot_cpu,properties=properties)

def main():
    container=json.loads((BASE/'g100_official/container.json').read_text(encoding='utf-8'))
    entries=container['entries'];known={}
    for e in entries:
        b=(ROOT/e['section_file']).read_bytes()
        assert len(b)==e['size'] and sha(b)==e['payload_sha256']==e['directory_sha256']
        known.setdefault(sha(b),[]).append(e)
    e=next(e for e in entries if e['name']=='dtb');b=(ROOT/e['section_file']).read_bytes();tree=parse_fdt(b)
    by={(r['path'],r['name']):r for r in tree['properties']}
    manifest=json.loads((ROOT/'analysis/verification_20261101/verification.json').read_text(encoding='utf-8'))
    matches=[];s5_dtb_rows=[]
    for name,m in manifest['images'].items():
        data=(ROOT/name).read_bytes();assert sha(data)==m['sha256']
        for part in m['partitions']:
            for other in known.get(part['stored_digest'],[]):
                if part['size']==other['size']:
                    matches.append(dict(image=name,partition=part['name'],g100_partition=other['name'],size=part['size'],flags=part['flags'],s5_payload_already_plaintext=part['digest_matches'],nonempty=part['size']>0,sha256=part['stored_digest'],g100_plaintext_file=other['section_file']))
            if part['name']=='dtb':s5_dtb_rows.append(dict(image=name,size=part['size'],expected_plaintext_sha256=part['stored_digest'],matches_g100_dtb=part['stored_digest']==e['directory_sha256'] and part['size']==len(b)))
    source_root=BASE/'official_oss_review/selected/linux-3.18.18'
    dts=(source_root/'arch/arm/boot/dts/pvc02v-dsc.dts').read_text(encoding='utf-8')
    dtsi=(source_root/'arch/arm/boot/dts/pvc02v.dtsi').read_text(encoding='utf-8')
    checks=[]
    for path,prop,expected in [('/', 'compatible',['panasonic,pvc02v-brb']),('/cpus/cpu@3','compatible',['arm,cortex-a7'])]:
        actual=by.get((path,prop),{}).get('strings');checks.append(dict(path=path,property=prop,expected=expected,actual=actual,matches=actual==expected))
    actual=by.get(('/memory@90200000','reg'),{}).get('cells_BE')
    checks.append(dict(path='/memory@90200000',property='reg',expected=[0,0x90200000,0,0x02f00000],actual=actual,matches=actual==[0,0x90200000,0,0x02f00000]))
    for path,prop,needle in [('/chosen','bootargs','root=/dev/mtdblock0'),('/chosen','bootargs','0x93100000'),('/chosen','bootargs','console=ttyAMA,115200')]:
        actual=' '.join(by.get((path,prop),{}).get('strings',[]));checks.append(dict(path=path,property=prop,source_substring=needle,actual=actual,matches=needle in actual and needle in dts))
    result=dict(g100_dtb_sha256=sha(b),g100_dtb_file=e['section_file'],g100_tree=tree,source_text_hashes={'pvc02v-dsc.dts':sha(dts.encode()),'pvc02v.dtsi':sha(dtsi.encode())},
        source_correspondence_checks=checks,all_checked_G100_source_correspondences=all(c['matches'] for c in checks),
        cross_image_known_plaintext_matches=matches,s5_dtb_sha_comparison=s5_dtb_rows,
        limits=['BSP and G100 FDT correspondence is not proof S5 uses the same board/addresses.',
                'Known plaintext digest matches do not recover a payload key.',
                'DTB is taken from authenticated-by-hash official G100 container; no hardware access or live S5 board discovery.'])
    (OUT/'source_dtb_binding.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('FDT_SOURCE_CHECKS',json.dumps(checks),flush=True)
    print('S5_DTB_COMPARE',json.dumps(s5_dtb_rows),flush=True)
    print('KNOWN_PLAINTEXT_MATCHES',json.dumps(matches),flush=True)
if __name__=='__main__':main()
