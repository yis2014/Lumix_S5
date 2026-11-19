"""Additional independent boundary/reference checks; synthetic data only."""
from pathlib import Path
import json
import eeprom_keyhunt_20261101 as E
import key_research_20261101 as K
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis'/'eeprom_keyhunt_20261101'
OUT.mkdir(exist_ok=True)
key=bytes.fromhex('603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4')
plaintext=(bytes(range(256))*257)[:65536+37]
checks=[]
for width,endian in E.SPECS:
    prefix=bytes(range(16-width))
    maximum=(1<<(width*8))-1
    start=maximum-1
    iv=prefix+start.to_bytes(width,endian)
    # Independent full-message ECB counter reference, not counter_crypt chunks.
    blocks=[]
    for i in range((len(plaintext)+15)//16):
        block=prefix+((start+i)&maximum).to_bytes(width,endian)
        blocks.append(block)
    assert blocks[2]==prefix+bytes(width)
    assert all(b[:16-width]==prefix for b in blocks)
    stream=K.aes(key,b''.join(blocks),True)
    expected=bytes(a^b for a,b in zip(plaintext,stream))
    actual=E.counter_crypt(key,plaintext,iv,width,endian)
    assert actual==expected
    assert E.counter_crypt(key,actual,iv,width,endian)==plaintext
    for i in (0,1,2,3,4095,4096):assert E.increment(iv,width,endian,i)==blocks[i]
    checks.append(dict(width_bytes=width,endian=endian,input_bytes=len(plaintext),
        wrap_after_two_blocks=True,retains_nonce_prefix=True,crosses_65536_boundary=True,
        partial_final_block=True,reference_matches=True,roundtrip=True))
result=dict(scope='Synthetic counter arithmetic and chunk-boundary verification; no real keys recovered.',checks=checks,all_passed=True)
(OUT/'counter_boundary_selftests.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
