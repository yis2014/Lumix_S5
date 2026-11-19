"""Verify a code-derived G100 initialization key against real S5 resources.
No success is recorded from source provenance or prefix alone.
"""
from pathlib import Path
import json,hashlib
from cryptography.hazmat.primitives.ciphers import modes
import eeprom_keyhunt_20261101 as E
import key_research_20261101 as K
from eeprom_layout_delta_20261101 import layouts
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis/eeprom_keyhunt_20261101/g100_official'
record=json.loads((OUT/'update_review/key_candidate_scatter.json').read_text(encoding='utf-8'))
key=bytes.fromhex(record['bytes']);program=(OUT/'sections/03_program_0.bin').read_bytes();container=(OUT/'G100_V13.bin').read_bytes()
assert program[0x8fe2b8:0x8fe2b8+16]==key and container[0x9124b8:0x9124b8+16]==key
assert K.sha(key)=='548c0f3ea729d3989db2a80afbbaeabe39310bc639442eae9695990a0f286945'
manifest=json.loads((ROOT/'analysis/verification_20261101/verification.json').read_text(encoding='utf-8'))
images={n:(ROOT/n).read_bytes() for n in manifest['images']}
for n,b in images.items():assert K.sha(b)==manifest['images'][n]['sha256']
targets=[];entries=[]
for label in ('eep_act_a','eep_act_b','ipu_data','koutei_kao','music'):
    plain=(ROOT/'analysis/william_review/plaintext_samples'/('rec_S5V29_'+label+'_from_G100.bin')).read_bytes()
    for n,m in manifest['images'].items():
        for e in m['partitions']:
            if e['name']==label and e['size']==len(plain) and e['stored_digest']==K.sha(plain) and e['flags']==3:
                targets.append(E.make_target(n,label,plain,images[n][e['file_offset']:e['end']]))
                entries.append(e)
assert len(targets)==11
matches=[];full=[];aux_cbc=[]
# Preserve explicit labels while deduplicating byte-identical transforms.
keys={}
for label,k in layouts(key):keys.setdefault(k,label)
for k,transform in keys.items():
    candidates,_=E.screen(k,targets,*E.prepare(targets))
    for i,mode,iv,spec in candidates:
        t=targets[i];result=dict(key_hex=k.hex(),transform=transform,image=t['image'],partition=t['partition'],mode=mode,iv=iv.hex() if iv is not None else None,counter_spec=spec)
        matches.append(result);plain=E.decode(k,t['cipher'],mode,iv,spec)
        if plain==t['plain'] and len(plain)==len(t['plain']) and K.sha(plain)==t['sha256']:
            full.append(dict(**result,full_sha256=K.sha(plain),full_length=len(plain)))
            print('FULL_RESOURCE_MATCH',json.dumps(full[-1]),flush=True)
    for t,e in zip(targets,entries):
        iv=bytes.fromhex(e['aux16'])
        plain=K.aes(k,t['cipher'],False,modes.CBC(iv))
        good=plain==t['plain'] and K.sha(plain)==t['sha256']
        aux_cbc.append(dict(transform=transform,image=t['image'],partition=t['partition'],iv=iv.hex(),full_matches=good,output_sha256=K.sha(plain)))
result=dict(candidate=record,candidate_sha256=K.sha(key),standard_AES_key_layouts_tested=len(keys),targets=len(targets),
    standard_AES_prefix_matches=matches,standard_AES_full_matches=full,standard_AES_CBC_directory_aux=aux_cbc,
    key_recovered_for_standard_AES=bool(full),
    scope='Only standard AES acceptance. Outer encoding=3 may use a distinct primitive; code-derived bytes alone are not acceptance.')
(OUT/'scatter_key_standard_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('FINAL',json.dumps(dict(standard_AES_full_matches=len(full),key_recovered_for_standard_AES=bool(full))),flush=True)
