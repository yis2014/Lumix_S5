"""Offline independent UPD inspection. Never modifies inputs or contacts devices."""
from pathlib import Path
import hashlib, struct, zlib, json, csv
import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis' / 'verification_20261101'
OUT.mkdir(exist_ok=True)
FILES = ['S5___V28.bin', 'S5___V29.bin', 'S5m2_V37.bin']

def sha(data):
    return hashlib.sha256(data).hexdigest()

def entropy(data):
    if not data:
        return 0.0
    counts = np.bincount(np.frombuffer(data, dtype=np.uint8), minlength=256)
    p = counts[counts > 0] / len(data)
    return float(-(p * np.log2(p)).sum())

def parse(name):
    data = (ROOT / name).read_bytes()
    assert data[:4] == b'UPD\0', 'Unexpected outer magic'
    header_size, body_size, expected_crc = struct.unpack_from('<III', data, 0x38)
    assert header_size == 0x200 and body_size + header_size == len(data)
    count = struct.unpack_from('<I', data, 0x2e8)[0]
    assert 0 < count < 1024 and 0x2ec + count * 92 <= len(data)
    rows, occurrences = [], {}
    for i in range(count):
        p = 0x2ec + 92 * i
        label = data[p:p+12].split(b'\0')[0].decode('ascii')
        occurrence = occurrences.get(label, 0)
        occurrences[label] = occurrence + 1
        off, size, target, flags = struct.unpack_from('<4I', data, p + 12)
        start, end = off + 0x200, off + 0x200 + size
        assert 0 <= start <= end <= len(data), (label, start, end)
        payload = data[start:end]
        stored = data[p+28:p+60].hex()
        computed = sha(payload)
        rows.append(dict(index=i, name=label, occurrence=occurrence,
            table_offset=p, file_offset=start, end=end, size=size,
            target_unknown=target, flags=flags, stored_digest=stored,
            payload_sha256=computed, digest_matches=computed == stored,
            aux16=data[p+60:p+76].hex(), tail16=data[p+76:p+92].hex(),
            entropy=entropy(payload), all_zero=bool(payload) and not any(payload),
            all_ff=bool(payload) and payload.count(255) == len(payload)))
    nonempty = sorted((r for r in rows if r['size']), key=lambda r:r['file_offset'])
    continuity = all(x['end'] == y['file_offset'] for x, y in zip(nonempty, nonempty[1:]))
    result = dict(file=name, size=len(data), sha256=sha(data),
        platform=data[0xc:0x20].split(b'\0')[0].decode('ascii'),
        crc_stored=expected_crc, crc_calculated=zlib.crc32(data[header_size:]),
        crc_matches=expected_crc == zlib.crc32(data[header_size:]),
        count=count, table_end=0x2ec + count * 92,
        payload_start=nonempty[0]['file_offset'], payload_end=nonempty[-1]['end'],
        contiguous=continuity, ends_at_eof=nonempty[-1]['end'] == len(data),
        partitions=rows)
    print(name, json.dumps({k:v for k,v in result.items() if k != 'partitions'}))
    return data, result

images, results = {}, {}
for name in FILES:
    images[name], results[name] = parse(name)
a, b = (images[n] for n in FILES[:2])
assert len(a) == len(b)
different = int(np.count_nonzero(np.frombuffer(a,dtype=np.uint8) != np.frombuffer(b,dtype=np.uint8)))
comparison=[]
for x,y in zip(results[FILES[0]]['partitions'], results[FILES[1]]['partitions']):
    assert (x['name'],x['occurrence']) == (y['name'],y['occurrence'])
    comparison.append(dict(name=x['name'],occurrence=x['occurrence'],
        file_offset=hex(x['file_offset']),size=x['size'],flags=x['flags'],
        layout_equal=all(x[k]==y[k] for k in ['file_offset','size','flags','target_unknown']),
        stored_digest_equal=x['stored_digest']==y['stored_digest'],
        raw_payload_equal=x['payload_sha256']==y['payload_sha256'],
        aux16_equal=x['aux16']==y['aux16']))
resources=[]
for p in sorted((ROOT/'analysis'/'william_review'/'plaintext_samples').glob('*.bin')):
    label=p.name.removeprefix('rec_S5V29_').removesuffix('_from_G100.bin')
    content=p.read_bytes(); digest=sha(content)
    matches={}
    for name,r in results.items():
        entries=[e for e in r['partitions'] if e['name']==label]
        matches[name]=[{'occurrence':e['occurrence'],'length_matches':len(content)==e['size'],
                        'stored_digest_matches':digest==e['stored_digest']} for e in entries]
    resources.append(dict(file=str(p.relative_to(ROOT)),name=label,size=len(content),sha256=digest,matches=matches))
lens=(ROOT/'400BV020.plf').read_bytes()
lens_result=dict(file='400BV020.plf',size=len(lens),sha256=sha(lens),entropy=entropy(lens),
    markers={s.decode('ascii'):lens.find(s) for s in [b'LENS-UPDATE-FILE-SOF:',b'LENS-UPDATE-FILE-EOH:',b'LUMIX S 20-60/F3.5-5.6',b'Panasonic']})
summary=dict(method='Offline byte-level revalidation; no decryption, device access, or key search.',
    images=results,comparison=dict(different_bytes=different,fraction=different/len(a),
    changed_directory_digests=[r['name'] for r in comparison if not r['stored_digest_equal']],partitions=comparison),
    known_resources=resources,lens=lens_result)
(OUT/'verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'s5_v28_v29.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(comparison[0]));w.writeheader();w.writerows(comparison)
print('DIFF',different, different/len(a))
print('CHANGED',summary['comparison']['changed_directory_digests'])
for name,r in results.items():
    print('FLAGS',name,{flag:{'count':sum(e['flags']==flag for e in r['partitions']),
        'digest_matches':sum(e['flags']==flag and e['digest_matches'] for e in r['partitions'])} for flag in [2,3]})
    for e in r['partitions']:
        if e['name'] in ['program','lut_data','lut2_data']:
            print('ANCHOR',name,json.dumps(e))
print('LENS',json.dumps(lens_result))
print('RESOURCE_CHECKS',json.dumps(resources))
