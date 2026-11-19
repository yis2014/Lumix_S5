"""Offline finite envelope checks with an existing known music resource.
Tests ONLY short repeating-XOR hypotheses. Does not brute-force AES or claim key recovery.
Reads firmware bytes; writes a new analysis JSON, never modifies firmware.
"""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parent;D=ROOT/'analysis'/'still_lut_port'
def sha(b):return hashlib.sha256(b).hexdigest()
def repeats(data,period):
    prefix=data[:min(len(data),65536+period)]
    if prefix!= (data[:period]*((len(prefix)+period-1)//period))[:len(prefix)]:return False
    return data==(data[:period]*((len(data)+period-1)//period))[:len(data)]
def main():
    report=json.loads((D/'container_comparison.json').read_text(encoding='utf-8'))
    plain=(ROOT/'analysis'/'william_review'/'plaintext_samples'/'rec_S5V29_music_from_G100.bin').read_bytes();ph=sha(plain)
    periods=[1,2,4,8,16,32,64,128,256,512,1024,2048,4096,8192,16384,32768,65536]
    result={'scope':'finite known-resource repeating-XOR tests only; not AES-mode detection or key recovery','resource_plaintext_bytes':len(plain),'resource_sha256':ph,'tested_periods':periods,'images':[],'cross_image':[],'key_recovered':False}
    masks=[];ciphers=[]
    for image in report['inputs']:
        e=next(x for x in image['entries'] if x['name']=='music')
        if e['directory_digest32']!=ph or e['size']!=len(plain):raise ValueError('Known resource identity/size not supported by directory')
        with (ROOT/image['file']).open('rb') as f:f.seek(e['file_offset']);cipher=f.read(e['size'])
        if sha(cipher)!=e['raw_sha256']:raise ValueError('Image payload changed since container comparison')
        mask=bytes(a^b for a,b in zip(plain,cipher));masks.append(mask);ciphers.append(cipher)
        result['images'].append({'file':image['file'],'resource_offset':e['file_offset'],'directory_digest_matches_known_resource':True,'raw_payload_sha256':sha(cipher),'raw_equals_known_resource':cipher==plain,'aux16_uninterpreted':e['aux16'],'supported_repeating_xor_periods':[p for p in periods if repeats(mask,p)]})
    for a,b in [(0,1),(1,2)]:
        delta=bytes(x^y for x,y in zip(ciphers[a],ciphers[b]));result['cross_image'].append({'a':result['images'][a]['file'],'b':result['images'][b]['file'],'raw_equal':ciphers[a]==ciphers[b],'hypothetical_keystream_equal':masks[a]==masks[b],'supported_periods_for_cross_image_xor':[p for p in periods if repeats(delta,p)]})
    result['limitations']=['Only exact tested periods/byte alignment rejected or supported; no exhaustive cipher search','P XOR C is a hypothetical XOR stream, not an AES key','No verified executable boot/decoder, algorithm, key derivation or load map obtained','Resource directory digest does not establish code or ISP compatibility']
    with (D/'resource_envelope_checks.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
