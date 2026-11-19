"""Finite hypothesis control: can common unsalted hashes of the verified G100
signature public key reproduce its actual scatter-initialized 16-byte constant?
No candidate is called a manufacturer KDF unless real evidence establishes it.
S5 receives follow-up candidates only if this G100 control has exact matches.
"""
from pathlib import Path
import json,hashlib
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from eeprom_layout_delta_20261101 import layouts
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'analysis/eeprom_keyhunt_20261101'
OUT=BASE/'public_derivation_control';OUT.mkdir(exist_ok=True)

def encodings(public):
    q=public.public_numbers();xb=q.x.to_bytes(32,'big');yb=q.y.to_bytes(32,'big');xl=xb[::-1];yl=yb[::-1]
    blobs={'xy_BE':xb+yb,'xy_LE':xl+yl,'yx_BE':yb+xb,'yx_LE':yl+xl,
           'x_BE':xb,'y_BE':yb,'x_LE':xl,'y_LE':yl,
           'sec1_uncompressed':public.public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint),
           'sec1_compressed':public.public_bytes(serialization.Encoding.X962,serialization.PublicFormat.CompressedPoint),
           'spki_DER':public.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo),
           'spki_PEM_LF':public.public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)}
    blobs['spki_PEM_CRLF']=blobs['spki_PEM_LF'].replace(b'\n',b'\r\n')
    blobs['spki_PEM_stripped']=blobs['spki_PEM_LF'].strip()
    return blobs

def main():
    key_info=json.loads((BASE/'g100_official/update_review/key_candidate_scatter.json').read_text(encoding='utf-8'))
    key=bytes.fromhex(key_info['bytes']);program=(BASE/'g100_official/sections/03_program_0.bin').read_bytes()
    container=json.loads((BASE/'g100_official/container.json').read_text(encoding='utf-8'))
    part=next(e for e in container['entries'] if e['name']=='program')
    assert hashlib.sha256(program).hexdigest()==part['payload_sha256']==part['directory_sha256']
    assert program[0x8fe2b8:0x8fe2b8+16]==key
    raw=program[0x7cd45e:0x7cd45e+64]
    public=ec.EllipticCurvePublicNumbers(int.from_bytes(raw[:32],'little'),int.from_bytes(raw[32:],'little'),ec.SECP256R1()).public_key()
    expected=serialization.load_pem_public_key((BASE/'g100_official/version_review/g100_metadata_public.pem').read_bytes())
    assert expected.public_numbers()==public.public_numbers()
    tested=0;hits=[];unique=set();inputs=[]
    for label,blob in encodings(public).items():
        inputs.append(dict(encoding=label,size=len(blob),sha256=hashlib.sha256(blob).hexdigest()))
        for alg in ('md5','sha1','sha224','sha256','sha384','sha512'):
            digest=hashlib.new(alg,blob).digest()
            for offset in range(len(digest)-15):
                value=digest[offset:offset+16]
                for layout,normal in layouts(value):
                    tested+=1;unique.add(normal)
                    if normal==key:hits.append(dict(public_encoding=label,hash=alg,digest_slice_start=offset,output_layout=layout))
    followups=[]
    if hits:
        s5=json.loads((BASE/'metadata_public_recovery/metadata_public_recovery_results.json').read_text(encoding='utf-8'))
        for item in s5['selected_s5_public_keys']:
            rawq=bytes.fromhex(item['public_raw64_BE']);q=ec.EllipticCurvePublicNumbers(int.from_bytes(rawq[:32],'big'),int.from_bytes(rawq[32:],'big'),ec.SECP256R1()).public_key()
            blobs=encodings(q)
            for recipe in hits:
                digest=hashlib.new(recipe['hash'],blobs[recipe['public_encoding']]).digest()
                value=digest[recipe['digest_slice_start']:recipe['digest_slice_start']+16]
                normalized=dict(layouts(value))[recipe['output_layout']]
                followups.append(dict(recipe=recipe,candidate_hex=normalized.hex(),status='Hypothesis only; requires S5 full resource/program verification.'))
    result=dict(hypothesis='Simple unsalted digest/encoding relation between signature public key and initialized 16B data constant; not an observed firmware KDF.',
        source_program_sha256=hashlib.sha256(program).hexdigest(),g100_initialized_constant_offset=0x8fe2b8,
        g100_initialized_constant_sha256=hashlib.sha256(key).hexdigest(),public_key_program_offset=0x7cd45e,
        public_encodings=inputs,hash_algorithms=['md5','sha1','sha224','sha256','sha384','sha512'],digest_windows='All contiguous16B slices',
        output_layouts='Eight finite explicit byte permutations',recipe_screenings=tested,unique_16B_outputs=len(unique),
        exact_G100_control_matches=hits,S5_followup_candidates=followups,manufacturer_KDF_established=False,
        limits=['Negative result excludes only this finite unsalted hash/encoding family.',
                'The target is G100 scatter initialization, not an independently verified encrypted-G100 payload key.',
                'A positive relation in one build would still need real S5 complete-resource verification.'])
    (OUT/'public_derivation_control.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['recipe_screenings','unique_16B_outputs','exact_G100_control_matches','S5_followup_candidates','manufacturer_KDF_established']},indent=2))
if __name__=='__main__':main()
