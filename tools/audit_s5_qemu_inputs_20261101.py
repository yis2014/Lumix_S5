"""Verify actual S5-only assets for emulation planning. Never runs firmware/SD/device.
Rejects treating container target_unknown as a runtime address or encrypted bytes as code.
"""
from pathlib import Path
import json,hashlib,struct
from cryptography.hazmat.primitives import serialization,hashes
from cryptography.hazmat.primitives.asymmetric import ec,utils
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'analysis/s5_qemu_20261101';OUT.mkdir(exist_ok=True)
manifest=json.loads((ROOT/'analysis/verification_20261101/verification.json').read_text(encoding='utf-8'))
public=serialization.load_pem_public_key((ROOT/'analysis/eeprom_keyhunt_20261101/metadata_public_recovery/S5_V28_V29_metadata_public_0ffaf83e958b.pem').read_bytes())
critical={'loader1','loader2','loader3','program','dtb','zimage','rootfs1','rootfs2'}
images=[]
for filename in ('S5___V28.bin','S5___V29.bin'):
    b=(ROOT/filename).read_bytes();m=manifest['images'][filename]
    assert len(b)==m['size'] and hashlib.sha256(b).hexdigest()==m['sha256']
    count=struct.unpack_from('<I',b,0x2e8)[0];end=0x2ec+count*92
    sig=utils.encode_dss_signature(int.from_bytes(b[0x220:0x240],'little'),int.from_bytes(b[0x240:0x260],'little'))
    digest=hashlib.sha256(b[0x2a0:end]).digest()[::-1]
    public.verify(sig,digest,ec.ECDSA(utils.Prehashed(hashes.SHA256())))
    rows=[]
    for p in m['partitions']:
        data=b[p['file_offset']:p['end']];h=hashlib.sha256(data).hexdigest();assert h==p['payload_sha256']
        matches=h==p['stored_digest']
        magics=dict(elf=data.startswith(b'\x7fELF'),squashfs_v4_le=data.startswith(b'hsqs'),fdt=data.startswith(b'\xd0\x0d\xfe\xed'),
            arm_zimage_magic_at_0x24=len(data)>=0x28 and struct.unpack_from('<I',data,0x24)[0]==0x016f2818)
        if p['name'] in critical or matches:
            rows.append(dict(name=p['name'],occurrence=p['occurrence'],size=p['size'],file_offset=p['file_offset'],flags=p['flags'],raw_matches_expected_plaintext_digest=matches,
                stored_sha256=h,expected_plaintext_sha256=p['stored_digest'],head16=data[:16].hex(),recognized_magics=magics,
                role='critical_boot_or_program_asset' if p['name'] in critical else 'other_matching_payload',
                verified_bootable=False,runtime_address=None,
                note='Container target_unknown deliberately not used as a load/entry address; byte signature alone would not prove bootability.'))
    missing=[n for n in sorted(critical) if not any(r['name']==n for r in rows)]
    images.append(dict(file=filename,sha256=m['sha256'],metadata_signature_verified=True,outer_encoding=struct.unpack_from('<I',b,0x34)[0],
        critical_names_missing=missing,assets=rows,critical_verified_plaintext=sum(r['name'] in critical and r['raw_matches_expected_plaintext_digest'] for r in rows)))
result=dict(scope='Actual DC-S5 V2.8/V2.9 only; no G100 analysis, no device/card access, no firmware execution.',images=images,
    interpretation='Neither generic QEMU virt nor emulated OTP supplies missing S5 decryption material. Valid original plaintext boot/target code and memory/peripheral contracts are separate prerequisites.',
    full_S5_boot_demonstrated=False,S5_parser_emulated=False,key_recovered=False)
(OUT/'input_readiness.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
for image in images:
    print(image['file'],'signature verified; critical verified plaintext:',image['critical_verified_plaintext'])
    for row in image['assets']:
        print(row['name'],row['occurrence'],row['size'],'plaintext_match=',row['raw_matches_expected_plaintext_digest'],'magic=',[k for k,v in row['recognized_magics'].items() if v])
