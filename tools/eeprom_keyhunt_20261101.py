"""Offline AES hypothesis testing of provenance-tracked EEPROM/SD candidates.
All input paths are workspace backups. No device access, card writes, network,
random padding candidates, or claim that Panasonic's encoding is AES.
"""
from pathlib import Path
import collections, hashlib, json, struct, time
import numpy as np
from cryptography.hazmat.primitives.ciphers import modes
import key_research_20261101 as K

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis'/'eeprom_keyhunt_20261101'
OUT.mkdir(parents=True,exist_ok=True)

def sha(b):return hashlib.sha256(b).hexdigest()
def xor(a,b):return K.xor(a,b)

def increment(block,width,endian,delta=1):
    return block[:-width]+((int.from_bytes(block[-width:],endian)+delta)%(1<<(width*8))).to_bytes(width,endian)
SPECS=[(w,e) for w in (16,8,4,2) for e in ('big','little')]

def counter_crypt(key,data,initial,width,endian):
    if width==16 and endian=='big':
        return K.aes(key,data,False,modes.CTR(initial))
    out=bytearray();index=0
    for start in range(0,len(data),65536):
        chunk=data[start:start+65536]
        count=(len(chunk)+15)//16
        counters=b''.join(increment(initial,width,endian,index+i) for i in range(count))
        stream=K.aes(key,counters,True)
        out.extend(xor(chunk,stream));index+=count
    return bytes(out)

def prepare(targets):
    dec=b''.join(t['cipher'][:32]+t['s1'] for t in targets)
    enc=b''.join(t['s1']+t['cipher'][:16] for t in targets)
    return dec,enc

def screen(key,targets,dec_blocks,enc_blocks):
    """Return prefix-hypothesis matches, never register a full success here."""
    dec=K.aes(key,dec_blocks,False);enc=K.aes(key,enc_blocks,True)
    candidates=[];ctr_blocks=[];ctr_groups=[]
    for i,t in enumerate(targets):
        d0,d1,ds=(dec[48*i+j:48*i+j+16] for j in (0,16,32))
        e_s,e_c=(enc[32*i+j:32*i+j+16] for j in (0,16))
        if d1==xor(t['cipher'][:16],t['plain'][16:32]):
            candidates.append((i,'CBC',xor(d0,t['plain'][:16]),None))
        if d0==t['plain'][:16] and d1==t['plain'][16:32]:
            candidates.append((i,'ECB',None,None))
        if e_s==t['s2']:candidates.append((i,'OFB',ds,None))
        if e_c==t['s2']:candidates.append((i,'CFB128',ds,None))
        unique={}
        for w,e in SPECS:unique.setdefault(increment(ds,w,e),[]).append((w,e))
        for next_state,specs in unique.items():
            ctr_blocks.append(next_state);ctr_groups.append((i,ds,specs))
    encoded=K.aes(key,b''.join(ctr_blocks),True)
    for j,(i,iv,specs) in enumerate(ctr_groups):
        if encoded[16*j:16*j+16]==targets[i]['s2']:
            for spec in specs:candidates.append((i,'CTR',iv,spec))
    return candidates,len(ctr_groups)

def decode(key,ct,mode,iv,spec):
    if mode=='CTR':return counter_crypt(key,ct,iv,*spec)
    mo={'CBC':lambda:modes.CBC(iv),'ECB':lambda:modes.ECB(),
        'OFB':lambda:modes.OFB(iv),'CFB128':lambda:modes.CFB(iv)}[mode]()
    return K.aes(key,ct,False,mo)

def make_target(image,name,plain,cipher):
    assert len(plain)==len(cipher) and len(plain)>=64
    return dict(image=image,partition=name,plain=plain,cipher=cipher,
                s1=xor(plain[:16],cipher[:16]),s2=xor(plain[16:32],cipher[16:32]),sha256=sha(plain))

def selftests():
    known=K.selftest()
    records=[];plaintext=bytes(range(256))*3
    for width in (16,24,32):
        key=bytes(range(width));iv=bytes.fromhex('6b0de937f1aa8c235dec4fb614893472')
        for mode in ('CBC','ECB','OFB','CFB128','CTR'):
            specs=SPECS if mode=='CTR' else [None]
            for spec in specs:
                if mode=='CTR':ct=counter_crypt(key,plaintext,iv,*spec)
                else:
                    mo={'CBC':lambda:modes.CBC(iv),'ECB':lambda:modes.ECB(),
                        'OFB':lambda:modes.OFB(iv),'CFB128':lambda:modes.CFB(iv)}[mode]()
                    ct=K.aes(key,plaintext,True,mo)
                # Multiple targets prove per-target batch offsets and mode grouping.
                dummy=make_target('SYNTHETIC_ONLY','negative',plaintext,bytes(len(plaintext)))
                target=make_target('SYNTHETIC_ONLY',mode,plaintext,ct)
                targets=[dummy,target,dummy]
                matches,_=screen(key,targets,*prepare(targets))
                selected=[m for m in matches if m[0]==1 and m[1]==mode and (mode!='CTR' or m[3]==spec)]
                assert selected,(width,mode,spec)
                assert all(decode(key,ct,m[1],m[2],m[3])==plaintext for m in selected)
                records.append(dict(key_bits=width*8,mode=mode,counter_spec=spec,passed=True))
    key=bytes.fromhex('2b7e151628aed2a6abf7158809cf4f3c')
    iv=bytes.fromhex('f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff')
    p=bytes.fromhex('6bc1bee22e409f96e93d7e117393172aae2d8a571e03ac9c9eb76fac45af8e51')
    c=bytes.fromhex('874d6191b620e3261bef6864990db6ce9806f66b7970fdff8617187bb9fffdff')
    assert counter_crypt(key,c,iv,16,'big')==p
    return dict(independent_standard_vectors=known,batch_and_unknown_iv_synthetic=records,
                synthetic_keys_never_added_to_real_pool=True)

def main():
    started=time.monotonic();self_test=selftests();print('SELFTEST PASS',flush=True)
    inventory=json.loads((ROOT/'analysis/sd_card_20261101/inventory_and_eeprom.json').read_text(encoding='utf-8'))
    manifest=json.loads((ROOT/'analysis/verification_20261101/verification.json').read_text(encoding='utf-8'))
    sources=[]
    # Distinct BE and LE representations preserve the exporter byte-order ambiguity.
    for e in inventory['eeprom']:
        for v in e['variants']:
            p=ROOT/v['file'];b=p.read_bytes();assert sha(b)==v['sha256']
            sources.append((str(p.relative_to(ROOT)),b,v['sha256']))
    # Private card files are low-entropy but their windows are cheap, reproducible
    # source hypotheses, not automatically secret key material.
    for r in inventory['files']:
        if '/PRIVATE/' in r['backup'].replace('\\','/'):
            p=ROOT/r['backup'];b=p.read_bytes();assert sha(b)==r['sha256']
            sources.append((str(p.relative_to(ROOT)),b,r['sha256']))
    pool={};source_counts=[]
    def add(key,source):
        if key not in pool:pool[key]=source
    for number,(name,b,digest) in enumerate(sources):
        before=len(pool)
        for width in (16,24,32):
            for off in range(len(b)-width+1):
                add(b[off:off+width],(number,off,width,'raw'))
        source_counts.append(dict(file=name,sha256=digest,size=len(b),new_unique=len(pool)-before))
        print('HARVEST',name,'unique',len(pool),flush=True)
    originals=list(pool.items())
    for key,src in originals:
        add(K.word_reverse(key),src[:3]+('reverse-u32',))
        add(key[::-1],src[:3]+('reverse-all',))
    del originals
    print('KEYS',len(pool),flush=True)
    images={name:(ROOT/name).read_bytes() for name in manifest['images']}
    for name,b in images.items():assert sha(b)==manifest['images'][name]['sha256']
    targets=[];target_sources=[]
    # Exact five known resource paths, no arbitrary filesystem enumeration.
    for label in ('eep_act_a','eep_act_b','ipu_data','koutei_kao','music'):
        p=ROOT/'analysis/william_review/plaintext_samples'/('rec_S5V29_'+label+'_from_G100.bin')
        plain=p.read_bytes();digest=sha(plain)
        for name,im in manifest['images'].items():
            for e in im['partitions']:
                if e['name']!=label or e['size']!=len(plain) or e['stored_digest']!=digest or e['flags']!=3:continue
                ct=images[name][e['file_offset']:e['end']]
                targets.append(make_target(name,label,plain,ct))
                target_sources.append(dict(image=name,partition=label,file_offset=e['file_offset'],size=len(plain),plaintext_sha256=digest,ciphertext_sha256=sha(ct)))
    dec_blocks,enc_blocks=prepare(targets)
    counts=collections.Counter();prefix_hits=[];full_matches=[];checked=0
    for key,source in pool.items():
        matches,ctr_tests=screen(key,targets,dec_blocks,enc_blocks)
        counts['CBC_unknown_IV_pairs']+=len(targets)
        counts['ECB_two_blocks']+=len(targets)
        counts['OFB_unknown_IV_pairs']+=len(targets)
        counts['CFB128_unknown_IV_pairs']+=len(targets)
        counts['CTR_unknown_initial_counter_spec_hypotheses']+=len(targets)*len(SPECS)
        counts['CTR_unique_second_counter_blocks']+=ctr_tests
        for i,mode,iv,spec in matches:
            t=targets[i];source_record=dict(file=sources[source[0]][0],offset=source[1],length=source[2],transform=source[3])
            info=dict(image=t['image'],partition=t['partition'],mode=mode,iv=iv.hex() if iv is not None else None,
                      counter_spec=spec,key_hex=key.hex(),key_source=source_record)
            prefix_hits.append(info)
            decoded=decode(key,t['cipher'],mode,iv,spec)
            if len(decoded)==len(t['plain']) and sha(decoded)==t['sha256'] and decoded==t['plain']:
                full_matches.append(dict(**info,full_sha256=sha(decoded),full_length=len(decoded)))
                print('FULL_RESOURCE_MATCH',json.dumps(full_matches[-1]),flush=True)
        checked+=1
        if checked%25000==0:
            progress=dict(phase='running',candidates_total=len(pool),candidates_checked=checked,targets=len(targets),
                prefix_hits=len(prefix_hits),full_verified_matches=len(full_matches),elapsed_seconds=time.monotonic()-started)
            (OUT/'progress.json').write_text(json.dumps(progress,indent=2),encoding='utf-8')
            print('PROGRESS',json.dumps(progress),flush=True)
    for name,b,digest in sources:assert sha((ROOT/name).read_bytes())==digest
    result=dict(scope='New SD-backup direct-key hypotheses; AES algorithm not independently established.',
        selftests=self_test,sources=source_counts,
        candidate_count=len(pool),candidate_count_by_bits=dict(collections.Counter(len(k)*8 for k in pool)),
        candidate_pool_sha256=sha(b''.join(sorted(pool))),
        candidate_rules=['All byte-stride 16/24/32B windows in six EEPROM renderings and seven private card backups',
                         'Each raw candidate also considered with u32-byte reversal and full-byte reversal',
                         'Global deduplication; constant candidates retained; no random keys, wordlists or arbitrary KDF guesses'],
        target_resources=target_sources,counts=dict(counts),prefix_matches=prefix_hits,
        full_verified_matches=full_matches,key_recovered=bool(full_matches),
        elapsed_seconds=time.monotonic()-started,source_backups_unchanged=True,
        limits=['Uses partition-start aligned actual known resource bytes; wrappers/compression/permuted ciphertext/chunk resets not covered.',
                'OFB, CFB128 and CBC candidates do not require guessing an IV; CTR derives first counter under each candidate.',
                'CTR tests last 16/8/4/2 bytes as BE or LE counters, not all custom counters.',
                'Paired-block prefix hit is not success until whole resource length/SHA and exact bytes match.',
                'Same key across all resources/models is not assumed.',
                'Negative result does not establish key absence or hardware OTP storage.'])
    (OUT/'eeprom_direct_key_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'progress.json').write_text(json.dumps(dict(phase='completed',candidates_checked=checked,candidates_total=len(pool),
        full_verified_matches=len(full_matches),elapsed_seconds=result['elapsed_seconds']),indent=2),encoding='utf-8')
    print('FINAL',json.dumps({k:result[k] for k in ['candidate_count','counts','key_recovered','elapsed_seconds']}),flush=True)
if __name__=='__main__':main()
