"""S5-only update differential. No decryption, patching, device or SD write.
Plaintext digests are authenticated by recovered common metadata public key.
"""
from pathlib import Path
import json,hashlib,struct
from cryptography.hazmat.primitives import serialization,hashes
from cryptography.hazmat.primitives.asymmetric import ec,utils
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'analysis/eeprom_keyhunt_20261101';OUT=BASE/'s5_entry_review';OUT.mkdir(exist_ok=True)
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    manifest=json.loads((ROOT/'analysis/verification_20261101/verification.json').read_text(encoding='utf-8'))
    public=serialization.load_pem_public_key((BASE/'metadata_public_recovery/S5_V28_V29_metadata_public_0ffaf83e958b.pem').read_bytes())
    data={};parts={};rows=[]
    for name in ('S5___V28.bin','S5___V29.bin'):
        b=(ROOT/name).read_bytes();m=manifest['images'][name];assert sha(b)==m['sha256']
        count=struct.unpack_from('<I',b,0x2e8)[0];end=0x2ec+92*count
        h=hashlib.sha256(b[0x2a0:end]).digest()[::-1];sig=utils.encode_dss_signature(int.from_bytes(b[0x220:0x240],'little'),int.from_bytes(b[0x240:0x260],'little'))
        public.verify(sig,h,ec.ECDSA(utils.Prehashed(hashes.SHA256())))
        data[name]=b;parts[name]={(p['name'],p['occurrence']):p for p in m['partitions']}
    left,right=list(data);assert set(parts[left])==set(parts[right])
    for key,p in parts[left].items():
        q=parts[right][key];a=data[left][p['file_offset']:p['end']];b=data[right][q['file_offset']:q['end']]
        rows.append(dict(name=key[0],occurrence=key[1],size_v28=p['size'],size_v29=q['size'],flags_v28=p['flags'],flags_v29=q['flags'],
            plaintext_digest_v28=p['stored_digest'],plaintext_digest_v29=q['stored_digest'],plaintext_digest_changed=p['stored_digest']!=q['stored_digest'],
            stored_bytes_changed=a!=b,iv_changed=p['aux16']!=q['aux16'],iv_v28=p['aux16'],iv_v29=q['aux16'],
            ciphertext_differing_bytes=sum(x!=y for x,y in zip(a,b))+abs(len(a)-len(b))))
    lens=ROOT/'400BV020.plf';b=lens.read_bytes()
    lens_info=dict(file=str(lens.relative_to(ROOT)),bytes=len(b),sha256=sha(b),first128_hex=b[:128].hex(),
        markers={x.decode():b.find(x) for x in (b'LENS-UPDATE-FILE-SOF:',b'LENS-UPDATE-FILE-EOH:',b'PSLFDH')},
        interpretation='Lens container distinct from body UPD. Header recognizability/version acceptance is not proof of unchecked payload or code execution.',
        modified=False)
    result=dict(images=[dict(file=n,sha256=sha(data[n]),metadata_signature_verified=True) for n in data],partition_count=len(rows),
        plaintext_changed=[r['name']+'#'+str(r['occurrence']) for r in rows if r['plaintext_digest_changed']],
        ciphertext_changed_count=sum(r['stored_bytes_changed'] for r in rows),iv_changed_count=sum(r['iv_changed'] for r in rows),partitions=rows,lens_sample=lens_info,
        limits=['Authenticated plaintext-digest changes localize changed partitions only, not functions or a specific CVE.',
                'Identical plaintext digest with different ciphertext/IV does not demonstrate a different key.',
                'Official V2.9 security release wording is separate external evidence, not proof every changed partition fixes a vulnerability.'])
    (OUT/'s5_v28_v29_authenticated_diff.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['partition_count','plaintext_changed','ciphertext_changed_count','iv_changed_count','lens_sample']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
