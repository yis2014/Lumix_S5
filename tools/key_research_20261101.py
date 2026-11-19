"""Offline, provenance-bounded AES hypotheses; does not assume UPD uses AES.
Scans AES schedules, tests clear-metadata keys, CBC with unknown IV, and
explicit stream initial-state hypotheses against actual complete resources.
No input writes, network, USB, random padding keys, or dictionary search.
"""
from pathlib import Path
import hashlib, json, struct, time, collections
import numpy as np
import cryptography
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis'/'key_research_20261101'
OUT.mkdir(exist_ok=True)
SBOX=bytes.fromhex('''
63 7c 77 7b f2 6b 6f c5 30 01 67 2b fe d7 ab 76
ca 82 c9 7d fa 59 47 f0 ad d4 a2 af 9c a4 72 c0
b7 fd 93 26 36 3f f7 cc 34 a5 e5 f1 71 d8 31 15
04 c7 23 c3 18 96 05 9a 07 12 80 e2 eb 27 b2 75
09 83 2c 1a 1b 6e 5a a0 52 3b d6 b3 29 e3 2f 84
53 d1 00 ed 20 fc b1 5b 6a cb be 39 4a 4c 58 cf
d0 ef aa fb 43 4d 33 85 45 f9 02 7f 50 3c 9f a8
51 a3 40 8f 92 9d 38 f5 bc b6 da 21 10 ff f3 d2
cd 0c 13 ec 5f 97 44 17 c4 a7 7e 3d 64 5d 19 73
60 81 4f dc 22 2a 90 88 46 ee b8 14 de 5e 0b db
e0 32 3a 0a 49 06 24 5c c2 d3 ac 62 91 95 e4 79
e7 c8 37 6d 8d d5 4e a9 6c 56 f4 ea 65 7a ae 08
ba 78 25 2e 1c a6 b4 c6 e8 dd 74 1f 4b bd 8b 8a
70 3e b5 66 48 03 f6 0e 61 35 57 b9 86 c1 1d 9e
e1 f8 98 11 69 d9 8e 94 9b 1e 87 e9 ce 55 28 df
8c a1 89 0d bf e6 42 68 41 99 2d 0f b0 54 bb 16
''')
assert len(SBOX)==256

def sha(b): return hashlib.sha256(b).hexdigest()
def xor(a,b): return bytes(x^y for x,y in zip(a,b))
def aes(key,data,encrypt=True,mode=None):
    c=Cipher(algorithms.AES(key),mode if mode is not None else modes.ECB())
    ctx=c.encryptor() if encrypt else c.decryptor()
    return ctx.update(data)+ctx.finalize()

def expand(key):
    nk=len(key)//4; nr=nk+6
    words=[key[i:i+4] for i in range(0,len(key),4)]; rc=1
    for i in range(nk,4*(nr+1)):
        t=words[-1]
        if i%nk==0:
            t=bytes(SBOX[x] for x in t[1:]+t[:1]);t=bytes([t[0]^rc])+t[1:]
            rc=((rc<<1)^ (0x11b if rc&0x80 else 0))&255
        elif nk>6 and i%nk==4:
            t=bytes(SBOX[x] for x in t)
        words.append(xor(words[i-nk],t))
    return b''.join(words)

def word_reverse(b):
    return b''.join(b[i:i+4][::-1] for i in range(0,len(b),4))

def scan_schedules(raw,label):
    """Every-byte offsets, forward schedules stored as byte or reversed-u32 words.
    Linear prefilter is only a hint; all 176/208/240 bytes must match expansion.
    Does not cover transformed/decryption schedules, split tables or hardware keys.
    """
    a=np.frombuffer(raw,dtype=np.uint8); records=[]; counts={}
    for nk in (4,6,8):
        total=16*(nk+7); n=len(a)-total+1
        if n<=0: continue
        mask=np.ones(n,dtype=bool)
        for j in range(4):
            mask &= (a[4*(nk+1)+j:4*(nk+1)+j+n] ^ a[4*nk+j:4*nk+j+n] ^ a[4+j:4+j+n])==0
        # Nonlinear first expanded-word byte in both word layouts. This also
        # removes constant padding without discarding keys whose bytes coincide.
        sb=np.frombuffer(SBOX,dtype=np.uint8)
        native=(a[4*nk:4*nk+n] ^ a[:n]) == (sb[a[4*(nk-1)+1:4*(nk-1)+1+n]] ^ 1)
        swapped=(a[4*nk+3:4*nk+3+n] ^ a[3:3+n]) == (sb[a[4*(nk-1)+2:4*(nk-1)+2+n]] ^ 1)
        mask &= native | swapped
        positions=np.flatnonzero(mask); counts[str(nk*32)]=len(positions)
        for off0 in positions:
            off=int(off0); window=raw[off:off+total]
            for layout,normalized in [('bytes',window),('reversed-u32',word_reverse(window))]:
                key=normalized[:nk*4]
                if expand(key)==normalized:
                    records.append(dict(file=label,offset=off,key_bits=nk*32,layout=layout,key_hex=key.hex()))
    return dict(file=label,bytes=len(raw),prefilter_hits=counts,fully_valid_schedules=records)

def selftest():
    key=bytes.fromhex('2b7e151628aed2a6abf7158809cf4f3c')
    p=bytes.fromhex('6bc1bee22e409f96e93d7e117393172aae2d8a571e03ac9c9eb76fac45af8e51')
    iv=bytes(range(16)); c=bytes.fromhex('7649abac8119b246cee98e9b12e9197d5086cb9b507219ee95db113a917678b2')
    assert aes(key,c,False,modes.CBC(iv))==p
    # FIPS-197 AES-128 key expansion, independently published final round.
    assert expand(bytes(range(16)))[-16:]==bytes.fromhex('13111d7fe3944a17f307a78b4d2b30c5')
    assert expand(bytes(range(24)))[-16:]==bytes.fromhex('a4970a331a78dc09c418c271e3a41d5d')
    assert expand(bytes(range(32)))[-16:]==bytes.fromhex('24fc79ccbf0979e9371ac23c6d68de36')
    ctr_iv=bytes.fromhex('f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff')
    ctr_ct=bytes.fromhex('874d6191b620e3261bef6864990db6ce9806f66b7970fdff8617187bb9fffdff')
    ofb_ct=bytes.fromhex('3b3fd92eb72dad20333449f8e83cfb4a7789508d16918f03f53c52dac54ed825')
    cfb_ct=bytes.fromhex('3b3fd92eb72dad20333449f8e83cfb4ac8a64537a0b3a93fcde3cdad9f1ce58b')
    assert aes(key,ctr_ct,False,modes.CTR(ctr_iv))==p
    assert aes(key,ofb_ct,False,modes.OFB(iv))==p
    assert aes(key,cfb_ct,False,modes.CFB(iv))==p
    assert aes(key,c[16:32],False)==xor(c[:16],p[16:32])
    assert xor(aes(key,c[:16],False),p[:16])==iv
    assert aes(key,c[17:33].ljust(16,b'\0'),False)!=xor(c[:16],p[16:32])
    schedule_tests=[]
    for width in (16,24,32):
        k=bytes(range(width)); schedule=expand(k)
        for layout,blob in [('bytes',schedule),('reversed-u32',word_reverse(schedule))]:
            r=scan_schedules(b'\xa7'*7+blob+b'\xb3'*19,'SYNTHETIC_SELFTEST_ONLY')
            assert any(x['offset']==7 and x['key_hex']==k.hex() for x in r['fully_valid_schedules'])
            schedule_tests.append(dict(bits=width*8,layout=layout,pass_test=True))
    return dict(nist_cbc=True,nist_ctr_ofb_cfb=True,fips197_expansion_128_192_256=True,cbc_unknown_iv=True,wrong_offset_negative=True,
                synthetic_schedule_tests=schedule_tests,synthetic_results_are_real_keys=False)

def main():
    start=time.monotonic();tests=selftest(); print('SELFTEST PASS',flush=True)
    names=['S5___V28.bin','S5___V29.bin','S5m2_V37.bin','400BV020.plf']
    images={n:(ROOT/n).read_bytes() for n in names}
    inputs={n:dict(size=len(b),sha256=sha(b)) for n,b in images.items()}
    manifest=json.loads((ROOT/'analysis'/'verification_20261101'/'verification.json').read_text(encoding='utf-8'))
    entries=manifest['images']; pool={}; candidate_counts={}; schedules=[]
    def add(k,source):
        if len(k) not in (16,24,32): return
        if k not in pool: pool[k]=source
    for name,data in images.items():
        print('SCHEDULE_SCAN',name,flush=True)
        r=scan_schedules(data,name);schedules.append(r)
        for hit in r['fully_valid_schedules']:add(bytes.fromhex(hit['key_hex']),hit)
    for name,im in entries.items():
        raw=images[name];assert sha(raw)==im['sha256']
        end=im['payload_start'];before=len(pool)
        for width in (16,24,32):
            for off in range(end-width+1):
                add(raw[off:off+width],dict(kind='raw-clear-metadata-window',file=name,offset=off,length=width))
        candidate_counts[name]=dict(metadata_range=[0,end],new_unique_candidates=len(pool)-before)
    # Byte-reversed and u32-endian representations of actual metadata words only.
    original=list(pool.items())
    for key,src in original:
        add(word_reverse(key),dict(kind='reverse-u32-candidate',original=src))
    for flag in ('zero','ff'):
        for width in (16,24,32):
            k=(b'\0' if flag=='zero' else b'\xff')*width
            pool.setdefault(k,dict(kind='explicit-constant-key-control-hypothesis',value=flag))
    targets=[]
    for p in sorted((ROOT/'analysis'/'william_review'/'plaintext_samples').glob('*.bin')):
        label=p.name.removeprefix('rec_S5V29_').removesuffix('_from_G100.bin')
        plain=p.read_bytes(); digest=sha(plain)
        for name,im in entries.items():
            matches=[e for e in im['partitions'] if e['name']==label and e['size']==len(plain) and e['stored_digest']==digest and e['flags']==3]
            for e in matches:
                off=e['file_offset'];c=images[name][off:off+e['size']]
                aux=bytes.fromhex(e['aux16'])
                # No claim these fields are actual IVs: list explicit states only.
                ivs=[('aux16',aux),('aux16+1-BE',((int.from_bytes(aux,'big')+1)%(1<<128)).to_bytes(16,'big')),
                     ('aux16+1-LE',((int.from_bytes(aux,'little')+1)%(1<<128)).to_bytes(16,'little')),
                     ('zero',bytes(16)),('one-BE',(1).to_bytes(16,'big')),
                     ('header80',images[name][0x80:0x90]),('aux16-reversed',aux[::-1])]
                # Deduplicate states, preserve labels for interpretation.
                ivs=list({v:n for n,v in ivs}.items())
                targets.append(dict(image=name,partition=label,plain=plain,cipher=c,entry=e,
                    ivs=[(n,v) for v,n in ivs],expected_stream=xor(c[:16],plain[:16]),
                    expected_cbc=xor(c[:16],plain[16:32]),digest=digest))
    print('CANDIDATES',len(pool),'TARGETS',len(targets),flush=True)
    dec_blocks=b''.join(t['cipher'][:32] for t in targets)
    enc_blocks=b''.join(iv for t in targets for _,iv in t['ivs'])
    hits=[];total_stream_states=sum(len(t['ivs']) for t in targets)
    def record(t,key,source,mode,iv,decoded):
        if len(decoded)==len(t['plain']) and sha(decoded)==t['digest'] and decoded==t['plain']:
            hits.append(dict(image=t['image'],partition=t['partition'],key_hex=key.hex(),source=source,
                 mode=mode,iv_hex=iv.hex() if iv is not None else None,full_sha256=sha(decoded),full_length=len(decoded)))
    for idx,(key,source) in enumerate(pool.items()):
        decrypted=aes(key,dec_blocks,False); encrypted=aes(key,enc_blocks,True);j=0
        for i,t in enumerate(targets):
            c=t['cipher'];p=t['plain'];d0=decrypted[32*i:32*i+16];d1=decrypted[32*i+16:32*i+32]
            if d1==t['expected_cbc']:
                iv=xor(d0,p[:16]);decoded=aes(key,c,False,modes.CBC(iv))
                record(t,key,source,'CBC-unknown-IV-recovered',iv,decoded)
            if d0==p[:16] and d1==p[16:32]:
                record(t,key,source,'ECB',None,aes(key,c,False))
            for state_name,iv in t['ivs']:
                first=encrypted[j:j+16];j+=16
                if first!=t['expected_stream']:continue
                for mode_name,mode in [('CTR-BE',modes.CTR(iv)),('OFB',modes.OFB(iv)),('CFB128',modes.CFB(iv))]:
                    if aes(key,c[:64],False,mode)!=p[:64]:continue
                    record(t,key,source,mode_name+':'+state_name,iv,aes(key,c,False,mode))
        if idx and idx%10000==0:print('TESTED',idx,'elapsed',round(time.monotonic()-start,2),flush=True)
    zero_target=next(t for t in targets if t['partition']=='ipu_data')
    z=zero_target['cipher'];zero_ecb=dict(image=zero_target['image'],partition='ipu_data',
        known_plaintext_all_zero=not any(zero_target['plain']),
        ciphertext_first_two_blocks_identical=z[:16]==z[16:32],
        conclusion='Direct AES-ECB without preprocessing is inconsistent with known all-zero resource when ciphertext blocks differ; does not exclude hybrid/chunked encoding.')
    for n,b in images.items():assert sha((ROOT/n).read_bytes())==inputs[n]['sha256']
    result=dict(scope='Conditional AES hypotheses and schedule scan; not a cipher identification or exhaustive key search.',
        inputs=inputs,cryptography_version=cryptography.__version__,selftests=tests,
        schedule_scan=schedules,candidate_count=len(pool),candidate_counts_by_bits=dict(collections.Counter(len(k)*8 for k in pool)),
        candidate_source_ranges=candidate_counts,candidate_pool_sha256=sha(b''.join(sorted(pool))),
        target_resources=[dict(image=t['image'],partition=t['partition'],size=len(t['plain']),sha256=t['digest']) for t in targets],
        tests=dict(cbc_unknown_iv=len(pool)*len(targets),ecb=len(pool)*len(targets),
                   stream_initial_states=len(pool)*total_stream_states),
        full_verified_matches=hits,key_recovered=bool(hits),zero_plaintext_ecb_check=zero_ecb,
        elapsed_seconds=time.monotonic()-start,original_inputs_unchanged=True,
        limits=['AES use is not established by these tests.',
        'No arbitrary KDF/hash/wordlist/random-padding candidates.',
        'CBC assumes exact known plaintext aligned at partition start and direct CBC encoding.',
        'Stream tests cover listed initial states, CTR full128 big-endian increments, OFB and CFB128 only.',
        'No chunk resets, byte permutations of payload, wrappers, compression before encryption, wrapped/hardware keys or general KDF tested.',
        'Schedule scan covers contiguous forward schedules and reversed-u32 storage, not all decryption/transformed schedules.',
        'Negative results reject only exact candidate+encoding hypotheses; no OTP/key absence conclusion.'])
    (OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('RESULT',json.dumps({k:result[k] for k in ['candidate_count','tests','key_recovered','full_verified_matches','elapsed_seconds']}),flush=True)
if __name__=='__main__':main()
