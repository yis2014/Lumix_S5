"""Check already-backed-up real S5 USB exports, with no new device traffic.
Candidates are internally unique windows/layouts of these source exports;
counts are not claimed globally new relative to previous EEPROM pools.
"""
from pathlib import Path
import json,time
import numpy as np
import reduced_aes5_keyhunt_20261101 as R
import emulate_g100_crypto_20261101 as M
import key_research_20261101 as K
from eeprom_layout_delta_20261101 import layouts
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'analysis/eeprom_keyhunt_20261101'
OUT=BASE/('usb_export_keyhunt_'+str(R.WIDTH*8));OUT.mkdir(exist_ok=True)

def main():
    begun=time.monotonic();selftests=R.test()
    source_dir=ROOT/'analysis/real_s5_20261030'
    historical=json.loads((source_dir/'experiment_manifest_after_properties.json').read_text(encoding='utf-8'))
    sources=[];raw_keys={}
    for r in historical['files']:
        if not r['file'].endswith('.bin'):continue
        path=source_dir/r['file'];data=path.read_bytes()
        assert len(data)==r['bytes'] and K.sha(data)==r['sha256']
        sources.append(dict(file=str(path.relative_to(ROOT)),sha256=K.sha(data),size=len(data)))
        for offset in range(len(data)-R.WIDTH+1):raw_keys.setdefault(data[offset:offset+R.WIDTH],(len(sources)-1,offset))
    keys={}
    for key,source in raw_keys.items():
        for transform,normalized in layouts(key):keys.setdefault(normalized,(*source,transform))
    del raw_keys
    keylist=list(keys)
    manifest=json.loads((ROOT/'analysis/verification_20261101/verification.json').read_text(encoding='utf-8'))
    images={n:(ROOT/n).read_bytes() for n in manifest['images']}
    for n,b in images.items():assert K.sha(b)==manifest['images'][n]['sha256']
    targets=[]
    for label in ('eep_act_a','eep_act_b','ipu_data','koutei_kao','music'):
        plain=(ROOT/'analysis/william_review/plaintext_samples'/('rec_S5V29_'+label+'_from_G100.bin')).read_bytes()
        for name,m in manifest['images'].items():
            for e in m['partitions']:
                if e['name']==label and e['size']==len(plain) and e['stored_digest']==K.sha(plain) and e['flags']==3:
                    targets.append((name,e,plain,images[name][e['file_offset']:e['end']]))
    assert len(targets)==11
    c2=b''.join(ct[16:32] for _,_,_,ct in targets)
    expect=np.frombuffer(b''.join(K.xor(ct[:16],p[16:32]) for _,_,p,ct in targets),dtype='<u4').reshape(-1,4)
    hits=[];resources=[];programs=[]
    for kind,nr in ((2,R.STANDARD_NR),(3,R.REDUCED_NR)):
        for start in range(0,len(keylist),4096):
            batch=keylist[start:start+4096];rk=R.schedules128(b''.join(batch),nr)
            out=R.decode_key_matrix(c2,rk);match=np.argwhere(np.all(out==expect[None,:,:],axis=2))
            for ki,ti in match:
                ki=int(ki);ti=int(ti);key=batch[ki];src,off,layout=keys[key]
                name,e,plain,ct=targets[ti];context=R.context_for(rk[ki])
                info=dict(image=name,partition=e['name'],key_hex=key.hex(),cipher_kind=kind,rounds=nr,
                    source=sources[src]['file'],source_offset=off,layout=layout)
                hits.append(info);decoded=M.cbc_decrypt(ct,context,bytes.fromhex(e['aux16']))
                if len(decoded)!=e['size'] or decoded!=plain or K.sha(decoded)!=e['stored_digest']:continue
                resources.append(dict(**info,full_sha256=K.sha(decoded),bytes_equal=True))
                pe=next(p for p in manifest['images'][name]['partitions'] if p['name']=='program')
                decoded_program=M.cbc_decrypt(images[name][pe['file_offset']:pe['end']],context,bytes.fromhex(pe['aux16']))
                good=len(decoded_program)==pe['size'] and K.sha(decoded_program)==pe['stored_digest']
                row=dict(image=name,key_hex=key.hex(),cipher_kind=kind,rounds=nr,program_sha256=K.sha(decoded_program),matches=good)
                if good:
                    dest=OUT/(Path(name).stem+'_program_verified.bin')
                    if dest.exists():assert dest.read_bytes()==decoded_program
                    else:
                        with dest.open('xb') as f:f.write(decoded_program)
                    row['file']=str(dest.relative_to(ROOT))
                programs.append(row)
        print('MODE_COMPLETE',R.WIDTH*8,kind,'rounds',nr,'candidates',len(keylist),'prefix',len(hits),flush=True)
    # Does any historical configuration export contain the newly recovered public components?
    public=json.loads((BASE/'metadata_public_recovery/metadata_public_recovery_results.json').read_text(encoding='utf-8'))
    public_locations=[]
    for source in sources:
        b=(ROOT/source['file']).read_bytes()
        for q in public['selected_s5_public_keys']:
            for endian in ('LE','BE'):
                xy=bytes.fromhex(q['public_raw64_'+endian])
                for part,needle in [('xy',xy),('x',xy[:32]),('y',xy[32:])]:
                    pos=b.find(needle)
                    while pos>=0:
                        public_locations.append(dict(file=source['file'],component=part,endian=endian,offset=pos));pos=b.find(needle,pos+1)
    result=dict(scope='Previously saved WPD real-camera exports only; no device connection or setting changes this round.',
        source_manifest_file=str((source_dir/'experiment_manifest_after_properties.json').relative_to(ROOT)),sources=sources,
        key_bits=R.WIDTH*8,selftests=selftests,unique_keys_within_USB_pool=len(keys),candidate_pool_sha256=K.sha(b''.join(sorted(keys))),
        global_new_key_count_claimed=False,mode_rounds={'2':R.STANDARD_NR,'3':R.REDUCED_NR},resource_targets=len(targets),
        CBC_second_block_screenings=len(keys)*len(targets)*2,prefix_hits=hits,full_resource_matches=resources,program_checks=programs,
        recovered_public_key_locations=public_locations,payload_decryption_key_recovered=any(r['matches'] for r in programs),
        elapsed_seconds=time.monotonic()-begun,
        limits=['Direct windows and eight layouts; no unsupported KDF assumptions.',
                'CBC only, standard and actual reduced-round semantics; cross-model applicability still needs a real full-resource match.',
                '13 historical source files include repeated exports and small property records, not 13 independent complete camera images.'])
    (OUT/'usb_export_keyhunt_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('FINAL',json.dumps({k:result[k] for k in ['key_bits','unique_keys_within_USB_pool','payload_decryption_key_recovered','elapsed_seconds']}),flush=True)
if __name__=='__main__':main()
