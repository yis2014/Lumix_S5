from pathlib import Path
import json,hashlib,re
ROOT=Path(__file__).resolve().parent;BASE=ROOT/'analysis/eeprom_keyhunt_20261101/g100_rootfs_review'
m=json.loads((BASE/'rootfs_inventory.json').read_text(encoding='utf-8'))
rows=[]
for r in m['entries']:
    if '/usr/pvc/' in r['path'] or any(s in r['path'] for s in ['iccdrv','icsmdrv','entropy.bin']):
        row=dict(r)
        if r['kind']=='file':
            b=(ROOT/r['output_file']).read_bytes();assert hashlib.sha256(b).hexdigest()==r['sha256']
            row['contains_s5_verification_public_key']=bytes.fromhex('9ed24846e6edf035766bb28d0210320929d819ba33d6e3dba8a745a89159671fcc531522c5ab8f23a6548fe0e4ca774523a196e9df58572699da0d78b8ea6891') in b
            row['contains_G100_initialized_constant']=bytes.fromhex('71143e939bc0784037dc4d3966de6d09') in b
        rows.append(row)
        print(r['section'],r['path'],r['size'],r.get('output_file',r.get('target_recorded_only','')))
(BASE/'proprietary_inventory.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
