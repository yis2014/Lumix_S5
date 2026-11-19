"""Direct AES-128 reduced-round candidate search using actual-code-derived
semantics. Vectorized key schedule/blocks independently checked against bounded
original ARM functions before any real candidate screens. No device writes.
"""
from pathlib import Path
import json,hashlib,time,collections,sys
import numpy as np
import emulate_g100_crypto_20261101 as M
import key_research_20261101 as K
from eeprom_layout_delta_20261101 import layouts
ROOT=Path(__file__).resolve().parent
WIDTH=int(sys.argv[1]) if len(sys.argv)>1 else 16
assert WIDTH in (16,24,32)
STANDARD_NR=WIDTH//4+6;REDUCED_NR=STANDARD_NR//2
OUT=M.BASE/('reduced_keyhunt' if WIDTH==16 else 'reduced_keyhunt_'+str(WIDTH*8));OUT.mkdir(exist_ok=True)
S=np.frombuffer(K.SBOX,dtype=np.uint8).astype(np.uint32)

def schedules128(keybytes,nr=None):
    if nr is None:nr=REDUCED_NR
    nk=WIDTH//4
    initial=np.frombuffer(keybytes,dtype='<u4').reshape(-1,nk)
    w=np.empty((len(initial),4*(nr+1)),dtype=np.uint32);w[:,:nk]=initial;rcon=1
    for i in range(nk,4*(nr+1)):
        t=w[:,i-1].copy()
        if i%nk==0:
            t=(t>>8)|(t<<24)
            t=S[t&255]|(S[(t>>8)&255]<<8)|(S[(t>>16)&255]<<16)|(S[t>>24]<<24)
            t=t^np.uint32(rcon);rcon=((rcon<<1)^(0x11b if rcon&128 else 0))&255
        elif nk==8 and i%nk==4:
            t=S[t&255]|(S[(t>>8)&255]<<8)|(S[(t>>16)&255]<<16)|(S[t>>24]<<24)
        w[:,i]=w[:,i-nk]^t
    d=w.reshape(-1,nr+1,4)[:,::-1,:].copy()
    t=d[:,1:-1,:].copy()
    d[:,1:-1,:]=M.TD[0][S[t&255]]^M.TD[1][S[(t>>8)&255]]^M.TD[2][S[(t>>16)&255]]^M.TD[3][S[t>>24]]
    return d

def decode_key_matrix(blocks,rk):
    nr=rk.shape[1]-1
    inp=np.frombuffer(blocks,dtype='<u4').reshape(-1,4)
    s=inp[None,:,:]^rk[:,None,0,:]
    for r in range(1,nr):
        new=np.empty_like(s)
        for c in range(4):new[:,:,c]=M.TD[0][s[:,:,c]&255]^M.TD[1][(s[:,:,(c+3)%4]>>8)&255]^M.TD[2][(s[:,:,(c+2)%4]>>16)&255]^M.TD[3][s[:,:,(c+1)%4]>>24]^rk[:,None,r,c]
        s=new
    new=np.empty_like(s)
    for c in range(4):new[:,:,c]=M.IS[s[:,:,c]&255]^(M.IS[(s[:,:,(c+3)%4]>>8)&255]<<8)^(M.IS[(s[:,:,(c+2)%4]>>16)&255]<<16)^(M.IS[s[:,:,(c+1)%4]>>24]<<24)^rk[:,None,nr,c]
    return new

def context_for(rk):return dict(rounds=rk.shape[0]-1,round_keys=rk.astype('<u4',copy=False).tobytes().hex())

def test():
    keys=[bytes(WIDTH),bytes([255])*WIDTH,bytes(range(WIDTH))]+[hashlib.sha256(('independent-schedule-key-'+str(i)).encode()).digest()[:WIDTH] for i in range(16)]
    emu=M.FirmwareCrypto();rows=[]
    blocks=b''.join(hashlib.sha256(('schedule-block-'+str(i)).encode()).digest()[:16] for i in range(5))
    for kind,nr in ((2,STANDARD_NR),(3,REDUCED_NR)):
        rk=schedules128(b''.join(keys),nr)
        batch=decode_key_matrix(blocks,rk)
        for i,key in enumerate(keys):
            actual=emu.setup(key,kind)
            assert actual['rounds']==nr and rk[i].astype('<u4').tobytes().hex()==actual['round_keys'],('schedule mismatch',kind,i)
            native=b''.join(emu.decrypt_block(blocks[j:j+16]) for j in range(0,len(blocks),16))
            assert batch[i].astype('<u4').tobytes()==native,('block mismatch',kind,i)
        rows.append(dict(kind=kind,rounds=nr,independent_key_schedules=len(keys),blocks_per_key=5,actual_ARM_agrees=True))
    assert not emu.invalid
    return rows

def main():
    begun=time.monotonic();tests=test();print('VECTORIZED_SCHEDULE_AND_BLOCK_SELFTEST_PASS',json.dumps(tests),flush=True)
    inv=json.loads((ROOT/'analysis/sd_card_20261101/inventory_and_eeprom.json').read_text(encoding='utf-8'))
    manifest=json.loads((ROOT/'analysis/verification_20261101/verification.json').read_text(encoding='utf-8'))
    src=[]
    for e in inv['eeprom']:
        for v in e['variants']:
            b=(ROOT/v['file']).read_bytes();assert K.sha(b)==v['sha256'];src.append((v['file'],b,v['sha256'],'EEPROM'))
    for r in inv['files']:
        if '/PRIVATE/' in r['backup'].replace('\\','/'):
            b=(ROOT/r['backup']).read_bytes();assert K.sha(b)==r['sha256'];src.append((r['backup'],b,r['sha256'],'card-private'))
    images={n:(ROOT/n).read_bytes() for n in manifest['images']}
    for n,b in images.items():
        assert K.sha(b)==manifest['images'][n]['sha256']
        src.append((n,b[:manifest['images'][n]['payload_start']],K.sha(b),'clear-metadata'))
    src.append((str((M.BASE/'sections/03_program_0.bin').relative_to(ROOT)),M.PROGRAM[0x8fe2b8:0x8fe2b8+WIDTH],K.sha(M.PROGRAM),'G100-scatter-key-only'))
    raw={}
    for i,(path,b,digest,kind) in enumerate(src):
        for off in range(len(b)-WIDTH+1):raw.setdefault(b[off:off+WIDTH],(i,off))
    candidates={}
    for key,source in raw.items():
        for label,normal in layouts(key):candidates.setdefault(normal,(source[0],source[1],label))
    del raw
    keys=list(candidates);print('CANDIDATES',len(keys),flush=True)
    targets=[]
    for label in ('eep_act_a','eep_act_b','ipu_data','koutei_kao','music'):
        expected=(ROOT/'analysis/william_review/plaintext_samples'/('rec_S5V29_'+label+'_from_G100.bin')).read_bytes()
        for name,m in manifest['images'].items():
            for e in m['partitions']:
                if e['name']==label and e['size']==len(expected) and e['stored_digest']==K.sha(expected) and e['flags']==3:
                    ct=images[name][e['file_offset']:e['end']];targets.append((name,e,expected,ct))
    assert len(targets)==11
    c2=b''.join(ct[16:32] for _,_,_,ct in targets)
    expected=np.frombuffer(b''.join(K.xor(ct[:16],p[16:32]) for _,_,p,ct in targets),dtype='<u4').reshape(-1,4)
    hits=[];verified=[];found={};checked=0;batchsize=4096
    for start in range(0,len(keys),batchsize):
        batchkeys=keys[start:start+batchsize];rk=schedules128(b''.join(batchkeys),REDUCED_NR)
        decoded=decode_key_matrix(c2,rk)
        match=np.all(decoded==expected[None,:,:],axis=2)
        for ki,ti in np.argwhere(match):
            key=batchkeys[int(ki)];name,e,plain_expected,ct=targets[int(ti)];source=candidates[key]
            path,_,digest,kind=src[source[0]]
            info=dict(image=name,partition=e['name'],key_hex=key.hex(),source_file=path,source_offset=source[1]+(0x8fe2b8 if kind.startswith('G100-scatter') else 0),
                transform=source[2],source_kind=kind,source_sha256=digest)
            hits.append(info);ctx=context_for(rk[int(ki)])
            iv=bytes.fromhex(e['aux16']);decoded_full=M.cbc_decrypt(ct,ctx,iv)
            if decoded_full!=plain_expected:
                first=M.decrypt_blocks(ct[:16],ctx);iv=K.xor(first,plain_expected[:16]);decoded_full=M.cbc_decrypt(ct,ctx,iv)
            if decoded_full==plain_expected and K.sha(decoded_full)==e['stored_digest'] and len(decoded_full)==e['size']:
                verified.append(dict(**info,iv_hex=iv.hex(),full_length=len(decoded_full),full_sha256=K.sha(decoded_full)))
                found[key]=ctx;print('FULL_KNOWN_RESOURCE_MATCH',json.dumps(verified[-1]),flush=True)
        checked+=len(batchkeys)
        if (start//batchsize)%10==0:print('PROGRESS',checked,'/',len(keys),'prefix',len(hits),'verified',len(verified),'elapsed',round(time.monotonic()-begun,2),flush=True)
        if found:break
    partition_results=[];programs=[]
    for key,ctx in found.items():
        for name,m in manifest['images'].items():
            for e in m['partitions']:
                if e['flags']!=3:continue
                data=images[name][e['file_offset']:e['end']];plain=M.cbc_decrypt(data,ctx,bytes.fromhex(e['aux16']))
                digest=K.sha(plain);good=(len(plain)==e['size'] and digest==e['stored_digest'])
                row=dict(image=name,partition=e['name'],file_offset=e['file_offset'],size=len(plain),key_hex=key.hex(),sha256=digest,expected_sha256=e['stored_digest'],matches=good)
                if good and e['name']=='program':
                    path=OUT/(Path(name).stem+'_program_verified.bin')
                    if path.exists():assert path.read_bytes()==plain
                    else:
                        with path.open('xb') as f:f.write(plain)
                    row['file']=str(path.relative_to(ROOT));programs.append(row)
                partition_results.append(row)
            print('IMAGE_FULL_SHA_RESULTS',name,sum(x['matches'] for x in partition_results if x['image']==name),'/',sum(x['image']==name for x in partition_results),flush=True)
    result=dict(scheme=f'Actual G100 encoding3 CBC primitive; {WIDTH*8}bit key setup reduced to {REDUCED_NR} rounds; S5 applicability requires full-resource validation',key_bits=WIDTH*8,rounds=REDUCED_NR,
        selftests=tests,candidate_count=len(keys),candidates_checked=checked,terminated_early_after_known_resource_match=checked<len(keys),
        candidate_pool_sha256=K.sha(b''.join(sorted(keys))),candidate_provenance='All selected-width byte-stride windows of six EEPROM representations, seven private-card backups, clear firmware metadata, eight explicit layouts, plus G100 scatter-initializer window; first provenance only.',
        source_manifest=[dict(file=p,sha256=h,kind=k,examined_bytes=len(b)) for p,b,h,k in src],
        targets=len(targets),CBC_second_block_screenings=checked*len(targets),prefix_hits=hits,full_known_resource_matches=verified,
        verified_keys_hex=[k.hex() for k in found],full_partition_results=partition_results,verified_programs=programs,
        key_recovered=bool(found and programs),elapsed_seconds=time.monotonic()-begun,
        limits=['Direct selected-width keys and finite layouts; not arbitrary KDF or masked/split key candidates.',
                'No matches does not establish key absence; algorithm was independently derived from G100, cross-model applicability still requires S5 full SHA.',
                'Known-resource success with inferred IV does not prove directory IV semantics in another model.'])
    (OUT/'reduced_keyhunt_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('FINAL',json.dumps({k:result[k] for k in ['candidate_count','candidates_checked','verified_keys_hex','key_recovered','elapsed_seconds']}),flush=True)
if __name__=='__main__':main()
