"""Recover ECDSA public-key candidates from known UPD metadata signatures.
This does not recover signing private keys or payload decryption keys.
Two independent S5 signatures select a common verification key only if their
candidate intersections and independent cryptography verification agree.
"""
from pathlib import Path
import json,struct,hashlib,time
from cryptography.hazmat.primitives.asymmetric import ec,utils
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.exceptions import InvalidSignature
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'analysis/eeprom_keyhunt_20261101'
OUT=BASE/'metadata_public_recovery';OUT.mkdir(exist_ok=True)
P=0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff
A=P-3;B=0x5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604b
N=0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551
G=(0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296,
   0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5)

def add(a,b):
    if a is None:return b
    if b is None:return a
    x,y=a;u,v=b
    if x==u and (y+v)%P==0:return None
    slope=((3*x*x+A)*pow(2*y,-1,P) if a==b else (v-y)*pow(u-x,-1,P))%P
    z=(slope*slope-x-u)%P
    return z,(slope*(x-z)-y)%P

def mul(k,point):
    result=None
    if k<0:return mul(-k,(point[0],(-point[1])%P))
    while k:
        if k&1:result=add(result,point)
        point=add(point,point);k>>=1
    return result

def recover(r,s,z):
    if not (0<r<N and 0<s<N):return []
    results=[]
    for j in range(2):
        x=r+j*N
        if x>=P:continue
        rhs=(pow(x,3,P)+A*x+B)%P;y=pow(rhs,(P+1)//4,P)
        if y*y%P!=rhs:continue
        for y in {y,(-y)%P}:
            point=(x,y)
            if mul(N,point) is not None:continue
            q=mul(pow(r,-1,N),add(mul(s,point),mul(-(z%N),G)))
            if q is not None:results.append(q)
    return results

def raw(q,endian='little'):return q[0].to_bytes(32,endian)+q[1].to_bytes(32,endian)
def verify(q,r,s,digest):
    try:
        public=ec.EllipticCurvePublicNumbers(q[0],q[1],ec.SECP256R1()).public_key()
        public.verify(utils.encode_dss_signature(r,s),digest,ec.ECDSA(utils.Prehashed(hashes.SHA256())))
        return True
    except (InvalidSignature,ValueError):return False

def main():
    start=time.monotonic();assert mul(N,G) is None
    # Independently compare point multiplication against the cryptography backend.
    for scalar in (1,2,3,17,0x123456789abcdef):
        q=mul(scalar,G);expected=ec.derive_private_key(scalar,ec.SECP256R1()).public_key().public_numbers()
        assert q==(expected.x,expected.y)
    manifest=json.loads((ROOT/'analysis/verification_20261101/verification.json').read_text(encoding='utf-8'))
    names=list(manifest['images'])
    g100=BASE/'g100_official/G100_V13.bin'
    source=json.loads((BASE/'g100_official/official_sample_source.json').read_text(encoding='utf-8'))
    inputs=[(str(g100.relative_to(ROOT)),source['bin_sha256'])]+[(n,manifest['images'][n]['sha256']) for n in names]
    candidates={};rows=[];messages={}
    for name,digest in inputs:
        data=(ROOT/name).read_bytes();assert hashlib.sha256(data).hexdigest()==digest
        count=struct.unpack_from('<I',data,0x2e8)[0];end=0x2ec+count*92
        assert end==0x2a0+0x4c+count*92
        message=data[0x2a0:end];h=hashlib.sha256(message).digest();signature=data[0x220:0x260]
        records=[];keys={}
        for endian in ('little','big'):
            r=int.from_bytes(signature[:32],endian);s=int.from_bytes(signature[32:],endian)
            for order in ('standard','reversed'):
                d=h if order=='standard' else h[::-1];z=int.from_bytes(d,'big')
                for q in recover(r,s,z):
                    assert verify(q,r,s,d)
                    identifier=raw(q,'big').hex()
                    entry=dict(public_raw64_BE=identifier,public_raw64_LE=raw(q).hex(),signature_scalar_endian=endian,digest_interpretation=order)
                    records.append(entry);keys.setdefault(identifier,[]).append(entry)
        rows.append(dict(file=name,file_sha256=digest,message_start=0x2a0,message_end=end,message_sha256=h.hex(),signature_raw64=signature.hex(),candidates=records))
        candidates[name]=keys;messages[name]=(message,h,signature)
        print('RECOVERED_CANDIDATES',name,len(keys),flush=True)
    # Original G100 key independently extracted from the linked descriptor.
    program=(BASE/'g100_official/sections/03_program_0.bin').read_bytes()
    known=program[0x7cd45e:0x7cd45e+64]
    q100=(int.from_bytes(known[:32],'little'),int.from_bytes(known[32:],'little'))
    assert raw(q100,'big').hex() in candidates[str(g100.relative_to(ROOT))]
    s5names=['S5___V28.bin','S5___V29.bin']
    assert messages[s5names[0]][0]!=messages[s5names[1]][0] and messages[s5names[0]][2]!=messages[s5names[1]][2]
    common=set(candidates[s5names[0]])&set(candidates[s5names[1]])
    selected=[];controls=[]
    for identifier in sorted(common):
        q=(int(identifier[:64],16),int(identifier[64:],16));matches=[]
        for name in names:
            message,h,sig=messages[name]
            for endian in ('little','big'):
                r=int.from_bytes(sig[:32],endian);s=int.from_bytes(sig[32:],endian)
                for order,d in [('standard',h),('reversed',h[::-1])]:
                    good=verify(q,r,s,d)
                    if good:matches.append(dict(file=name,signature_scalar_endian=endian,digest_interpretation=order,verified=True))
        assert all(any(m['file']==n for m in matches) for n in s5names)
        common_formats=set.intersection(*(set((m['signature_scalar_endian'],m['digest_interpretation']) for m in matches if m['file']==n) for n in s5names))
        assert common_formats
        public=ec.EllipticCurvePublicNumbers(q[0],q[1],ec.SECP256R1()).public_key()
        tag='S5_V28_V29_metadata_public_'+hashlib.sha256(bytes.fromhex(identifier)).hexdigest()[:12]
        artifacts={tag+'.pem':public.public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo),
                   tag+'.der':public.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo),
                   tag+'_raw64_LE.bin':raw(q),tag+'_raw64_BE.bin':raw(q,'big')}
        for fn,b in artifacts.items():
            p=OUT/fn
            if p.exists():assert p.read_bytes()==b
            else:
                with p.open('xb') as f:f.write(b)
        for m in matches:
            name=m['file'];message,h,sig=messages[name];order=m['digest_interpretation'];endian=m['signature_scalar_endian']
            d=h if order=='standard' else h[::-1];r=int.from_bytes(sig[:32],endian);s=int.from_bytes(sig[32:],endian)
            changed=bytearray(message);changed[0x4c]^=1;dh=hashlib.sha256(changed).digest();dh=dh if order=='standard' else dh[::-1]
            header_changed=bytearray(message);header_changed[0]^=1;hh=hashlib.sha256(header_changed).digest();hh=hh if order=='standard' else hh[::-1]
            assert not verify(q,r,s,dh) and not verify(q,r,s^1,d) and not verify(q,r,s,hh)
            controls.append(dict(file=name,original_verifies=True,directory_one_bit_rejected=True,directory_mutation_file_offset=0x2ec,signature_one_bit_rejected=True,repeated_header_one_bit_rejected=True))
        selected.append(dict(public_raw64_BE=identifier,public_raw64_LE=raw(q).hex(),verified_images=matches,
            common_verification_parameters=[dict(signature_scalar_endian=a,digest_interpretation=b) for a,b in sorted(common_formats)],
            artifacts=[dict(file=str((OUT/f).relative_to(ROOT)),sha256=hashlib.sha256(b).hexdigest()) for f,b in artifacts.items()]))
    # Locate recovered public components in related local evidence, not secrets.
    scan_sources=[]
    inventory=json.loads((BASE.parent/'sd_card_20261101/inventory_and_eeprom.json').read_text(encoding='utf-8'))
    for e in inventory['eeprom']:
        for v in e['variants']:scan_sources.append(v['file'])
    scan_sources.append(str((BASE/'g100_official/G100_V13.bin').relative_to(ROOT)))
    locations=[]
    for name in scan_sources:
        b=(ROOT/name).read_bytes()
        for key in selected:
            q=(int(key['public_raw64_BE'][:64],16),int(key['public_raw64_BE'][64:],16))
            for endian in ('little','big'):
                components={'xy':raw(q,endian),'x':q[0].to_bytes(32,endian),'y':q[1].to_bytes(32,endian)}
                for comp,needle in components.items():
                    pos=b.find(needle)
                    while pos>=0:
                        locations.append(dict(file=name,component=comp,endian=endian,offset=pos));pos=b.find(needle,pos+1)
    result=dict(purpose='Recover and verify metadata PUBLIC keys only; not decryption keys/private signing keys.',
        curve='secp256r1',point_arithmetic_checked_against_cryptography=True,g100_known_public_control_passed=True,
        input_signatures=rows,s5_two_signature_intersection_count=len(common),selected_s5_public_keys=selected,negative_controls=controls,
        recovered_public_key_locations=locations,s5_public_key_uniquely_recovered=len(selected)==1,
        payload_decryption_key_recovered=False,private_key_recovered=False,elapsed_seconds=time.monotonic()-start)
    (OUT/'metadata_public_recovery_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('FINAL',json.dumps({k:result[k] for k in ['s5_two_signature_intersection_count','s5_public_key_uniquely_recovered','payload_decryption_key_recovered','elapsed_seconds']}),flush=True)
if __name__=='__main__':main()
