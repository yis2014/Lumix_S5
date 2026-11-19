"""Bounded source-window scan of the validated official G100 program.
Counts are window/layout screenings, NOT unique keys or brute-force keyspace.
General cipher behavior is independently verified against actual ARM first.
"""
from pathlib import Path
import sys,json,time,hashlib
import numpy as np
import reduced_aes5_keyhunt_20261101 as R
import emulate_g100_crypto_20261101 as M
import key_research_20261101 as K
from eeprom_layout_delta_20261101 import layouts
ROOT=Path(__file__).resolve().parent
WIDTH=R.WIDTH;OUT=M.BASE/('program_window_scan_'+str(WIDTH*8));OUT.mkdir(exist_ok=True)

def main():
    begun=time.monotonic();tests=R.test()
    print('ACTUAL_ARM_CROSSCHECK_PASS',WIDTH*8,json.dumps(tests),flush=True)
    manifest=json.loads((ROOT/'analysis/verification_20261101/verification.json').read_text(encoding='utf-8'))
    images={n:(ROOT/n).read_bytes() for n in manifest['images']}
    for n,b in images.items():assert K.sha(b)==manifest['images'][n]['sha256']
    plain=(ROOT/'analysis/william_review/plaintext_samples/rec_S5V29_music_from_G100.bin').read_bytes()
    targets=[]
    for name,m in manifest['images'].items():
        e=next(e for e in m['partitions'] if e['name']=='music')
        assert K.sha(plain)==e['stored_digest'] and len(plain)==e['size']
        ct=images[name][e['file_offset']:e['end']];targets.append((name,e,ct))
    c2=b''.join(ct[16:32] for _,_,ct in targets)
    expected=np.frombuffer(b''.join(K.xor(ct[:16],plain[16:32]) for _,_,ct in targets),dtype='<u4').reshape(-1,4)
    windows=np.lib.stride_tricks.sliding_window_view(np.frombuffer(M.PROGRAM,dtype=np.uint8),WIDTH)
    # Examine the known scatter-initialized .data first, then every other offset.
    first_lo=0x8d9c7c;first_hi=0x8d9c7c+0x29f34
    first_hi=min(first_hi,len(windows))
    intervals=[(first_lo,first_hi),(0,first_lo),(first_hi,len(windows))]
    permutations=[]
    for label,permuted in layouts(bytes(range(WIDTH))):permutations.append((label,np.frombuffer(permuted,dtype=np.uint8).astype(np.int64)))
    screened=0;prefix=[];full_resources=[];program_checks=[];found={};sequence_hash=hashlib.sha256();stop=False
    BATCH=8192
    for lo,hi in intervals:
        for offset in range(lo,hi,BATCH):
            batch=windows[offset:min(offset+BATCH,hi)]
            for label,perm in permutations:
                keybytes=batch[:,perm].tobytes(order='C');sequence_hash.update(keybytes)
                rk=R.schedules128(keybytes,R.REDUCED_NR)
                decoded=R.decode_key_matrix(c2,rk)
                matches=np.argwhere(np.all(decoded==expected[None,:,:],axis=2))
                for ki,ti in matches:
                    ki=int(ki);ti=int(ti);candidate=keybytes[ki*WIDTH:(ki+1)*WIDTH]
                    name,e,ct=targets[ti];context=R.context_for(rk[ki]);iv=bytes.fromhex(e['aux16'])
                    info=dict(image=name,partition='music',key_hex=candidate.hex(),program_source_offset=offset+ki,transform=label,key_bits=WIDTH*8)
                    prefix.append(info)
                    decoded_full=M.cbc_decrypt(ct,context,iv)
                    if decoded_full!=plain:
                        iv=K.xor(M.decrypt_blocks(ct[:16],context),plain[:16]);decoded_full=M.cbc_decrypt(ct,context,iv)
                    if decoded_full!=plain or K.sha(decoded_full)!=e['stored_digest']:continue
                    full_resources.append(dict(**info,plaintext_sha256=K.sha(decoded_full),bytes=len(decoded_full),iv_hex=iv.hex()))
                    print('REAL_RESOURCE_MATCH',json.dumps(full_resources[-1]),flush=True)
                    pe=next(e for e in manifest['images'][name]['partitions'] if e['name']=='program')
                    ciphertext=images[name][pe['file_offset']:pe['end']]
                    prog=M.cbc_decrypt(ciphertext,context,bytes.fromhex(pe['aux16']))
                    good=len(prog)==pe['size'] and K.sha(prog)==pe['stored_digest']
                    row=dict(image=name,key_hex=candidate.hex(),size=len(prog),sha256=K.sha(prog),expected_sha256=pe['stored_digest'],matches=good)
                    if good:
                        p=OUT/(Path(name).stem+'_program_verified.bin')
                        if p.exists():assert p.read_bytes()==prog
                        else:
                            with p.open('xb') as f:f.write(prog)
                        row['file']=str(p.relative_to(ROOT));found[candidate]=context;stop=True
                    program_checks.append(row)
                screened+=len(batch)
                if stop:break
            if screened%(BATCH*8*64)<BATCH*8 or stop:
                progress=dict(key_bits=WIDTH*8,window_layout_screenings=screened,max_screenings=len(windows)*len(permutations),
                    current_source_offset=offset,prefix_hits=len(prefix),full_resource_matches=len(full_resources),program_matches=sum(x['matches'] for x in program_checks),elapsed_seconds=time.monotonic()-begun)
                (OUT/'progress.json').write_text(json.dumps(progress,indent=2),encoding='utf-8');print('PROGRESS',json.dumps(progress),flush=True)
            if stop:break
        if stop:break
    # Cross-image verification after a real program match, never assume universality.
    cross=[]
    for key,context in found.items():
        for name,m in manifest['images'].items():
            for e in m['partitions']:
                if e['flags']!=3:continue
                data=images[name][e['file_offset']:e['end']];decoded=M.cbc_decrypt(data,context,bytes.fromhex(e['aux16']))
                cross.append(dict(image=name,partition=e['name'],key_hex=key.hex(),size=len(decoded),sha256=K.sha(decoded),matches=K.sha(decoded)==e['stored_digest']))
    result=dict(source_file=str((M.BASE/'sections/03_program_0.bin').relative_to(ROOT)),source_sha256=K.sha(M.PROGRAM),source_bytes=len(M.PROGRAM),
        key_bits=WIDTH*8,rounds=R.REDUCED_NR,selftests=tests,source_intervals=intervals,window_stride=1,layouts=[l for l,_ in permutations],
        source_window_count=len(windows),window_layout_screenings=screened,max_window_layout_screenings=len(windows)*len(permutations),
        CBC_second_block_screenings=screened*len(targets),targets=[n for n,_,_ in targets],
        candidate_sequence_sha256=sequence_hash.hexdigest(),counts_are_unique_keys=False,completed_full_source_scan=not stop,
        prefix_hits=prefix,full_resource_matches=full_resources,program_checks=program_checks,verified_keys_hex=[k.hex() for k in found],
        cross_image_partition_checks=cross,key_recovered=bool(found),elapsed_seconds=time.monotonic()-begun,
        limits=['Source is official G100 code/data, not S5 code or arbitrary derived/masked keys.',
                'Three music targets screen one resource per image, based on a global per-container key hypothesis; not every per-partition-key hypothesis.',
                'Cross-model applicability requires full resource and program SHA matches. No keys are reported from counts or source provenance alone.'])
    (OUT/'program_scan_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('FINAL',json.dumps({k:result[k] for k in ['key_bits','window_layout_screenings','verified_keys_hex','key_recovered','elapsed_seconds']}),flush=True)
if __name__=='__main__':main()
