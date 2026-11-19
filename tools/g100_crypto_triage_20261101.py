"""Offline constants/schedule provenance triage of validated official G100.
Constant matches are not secret keys; only complete resource validation counts.
"""
from pathlib import Path
import hashlib,json,struct,collections,time
import key_research_20261101 as K
import eeprom_keyhunt_20261101 as E
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'analysis/eeprom_keyhunt_20261101/g100_official'
OUT=BASE/'crypto_review';OUT.mkdir(exist_ok=True)

def hits(data,needle):
    out=[];pos=0
    while True:
        pos=data.find(needle,pos)
        if pos<0:return out
        out.append(pos);pos+=1

def main():
    start=time.monotonic();manifest=json.loads((BASE/'container.json').read_text(encoding='utf-8'))
    inv=bytearray(256)
    for i,b in enumerate(K.SBOX):inv[b]=i
    signatures={'AES_SBOX_full256':K.SBOX,'AES_INVERSE_SBOX_full256':bytes(inv),
        'UPD_magic':b'UPD\0','panasonic_literal':b'panasonic','decrypt_literal':b'decrypt',
        'AES_literal':b'AES','ecdsa_literal':b'ecdsa','keyslot_literal':b'keyslot'}
    rcon=[1,2,4,8,16,32,64,128,27,54]
    signatures['AES_RCON_u32_BE_highbyte']=struct.pack('>10I',*(n<<24 for n in rcon))
    signatures['AES_RCON_u32_LE_lowbyte']=struct.pack('<10I',*rcon)
    table=[]
    for s in K.SBOX:
        d=((s<<1)^(0x11b if s&128 else 0))&255
        table.append(bytes([d,s,s,d^s]))
    t=b''.join(table)
    signatures['AES_TE_full1024']=t;signatures['AES_TE_full1024_u32reverse']=K.word_reverse(t)
    sha_k=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5]
    signatures['SHA256_K_first8_LE']=struct.pack('<8I',*sha_k)
    signatures['SHA256_K_first8_BE']=struct.pack('>8I',*sha_k)
    selected={'loader1','loader2','loader3','program','postboot1','postboot2','postboot5','zboot','apu_boot'}
    rows=[];keys={}
    for e in manifest['entries']:
        if e['name'] not in selected:continue
        data=(ROOT/e['section_file']).read_bytes();assert K.sha(data)==e['directory_sha256']
        found={n:hits(data,s) for n,s in signatures.items()}
        found={k:v for k,v in found.items() if v}
        schedule=K.scan_schedules(data,e['section_file'])
        for h in schedule['fully_valid_schedules']:keys.setdefault(bytes.fromhex(h['key_hex']),h)
        refs=[]
        if e['name']=='program':
            for signature in ('AES_SBOX_full256','AES_INVERSE_SBOX_full256','AES_TE_full1024','AES_TE_full1024_u32reverse'):
                for pos in found.get(signature,[]):
                    for base in (0,e['target_unknown'],0x04a80000,0x04a00000):
                        ptr=base+pos
                        if ptr>0xffffffff:continue
                        matches=hits(data,struct.pack('<I',ptr))
                        if matches:refs.append(dict(signature=signature,table_relative_offset=pos,base_hypothesis=base,pointer=ptr,literal_offsets=matches))
        row=dict(name=e['name'],file=e['section_file'],sha256=K.sha(data),size=len(data),
                 head64_hex=data[:64].hex(),signature_hits=found,literal_references_by_base_hypothesis=refs,schedule_scan=schedule)
        rows.append(row);print('SECTION',e['name'],json.dumps(found),'schedules',len(schedule['fully_valid_schedules']),flush=True)
    targets=[];s5=json.loads((ROOT/'analysis/verification_20261101/verification.json').read_text(encoding='utf-8'))
    images={n:(ROOT/n).read_bytes() for n in s5['images']}
    for name,data in images.items():assert K.sha(data)==s5['images'][name]['sha256']
    for label in ('eep_act_a','eep_act_b','ipu_data','koutei_kao','music'):
        plain=(ROOT/'analysis/william_review/plaintext_samples'/('rec_S5V29_'+label+'_from_G100.bin')).read_bytes()
        g=[e for e in manifest['entries'] if e['name']==label]
        if g:assert len(plain)==g[0]['size'] and K.sha(plain)==g[0]['directory_sha256']
        for name,im in s5['images'].items():
            for e in im['partitions']:
                if e['name']==label and e['size']==len(plain) and e['stored_digest']==K.sha(plain) and e['flags']==3:
                    targets.append(E.make_target(name,label,plain,images[name][e['file_offset']:e['end']]))
    assert len(targets)==11
    prefix=[];verified=[]
    for key,source in keys.items():
        matches,_=E.screen(key,targets,*E.prepare(targets))
        for i,mode,iv,spec in matches:
            t=targets[i];record=dict(key_hex=key.hex(),source=source,image=t['image'],partition=t['partition'],mode=mode,iv_hex=iv.hex() if iv is not None else None,counter_spec=spec)
            prefix.append(record);plain=E.decode(key,t['cipher'],mode,iv,spec)
            if plain==t['plain'] and K.sha(plain)==t['sha256']:verified.append(dict(**record,full_sha256=K.sha(plain)))
    result=dict(scope='Actual official G100 code/constants, not a claim that G100 and S5 use the same keys.',
        g100_sample_sha256=manifest['sha256'],entries=rows,schedule_keys_count=len(keys),
        schedule_keys_tested_against_s5=True,prefix_matches=prefix,full_verified_matches=verified,key_recovered=bool(verified),
        elapsed_seconds=time.monotonic()-start,
        limits=['Constant tables identify primitive implementations, not secret key material or firmware-update use.',
                'Schedule scan covers contiguous forward expanded keys in two u32 layouts only.',
                'Literal base hypotheses are search aids, not established runtime addresses.',
                'Indirect callers, hardware keyslots and external dependencies require actual code-flow review.'])
    (OUT/'crypto_triage.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('FINAL',json.dumps({k:result[k] for k in ['schedule_keys_count','key_recovered','elapsed_seconds']}),flush=True)
if __name__=='__main__':main()
