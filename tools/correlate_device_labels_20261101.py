"""Correlate user-provided body labels with existing offline card backups.
No serial-number web queries; report only a masked serial/fingerprint.
No guessed serial-to-key formula is treated as camera code evidence.
"""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis/eeprom_keyhunt_20261101'
SERIAL='WJ2HB002960'
LABELS={'body_serial':SERIAL,'marketing_model':'DC-S5','regulatory_model':'P2004A','radio_approval':'2020AP7120'}
manifest=json.loads((ROOT/'analysis/sd_card_20261101/inventory_and_eeprom.json').read_text(encoding='utf-8'))
paths=[]
for e in manifest['eeprom']:
    for v in e['variants']:paths.append((v['file'],v['sha256'],'EEPROM reconstruction'))
for e in manifest['files']:
    if Path(e['backup']).name.upper() in ('S5A.TXT','S5F.TXT','S5U.TXT'):paths.append((e['backup'],e['sha256'],'original export'))
results=[]
for name,digest,kind in paths:
    raw=(ROOT/name).read_bytes();assert hashlib.sha256(raw).hexdigest()==digest
    matches=[]
    for label,value in LABELS.items():
        for encoding in ('ascii','utf-16-le','utf-16-be'):
            needle=value.encode(encoding);start=0
            while True:
                pos=raw.find(needle,start)
                if pos<0:break
                matches.append(dict(label=label,encoding=encoding,offset=pos,length=len(needle)));start=pos+1
    results.append(dict(file=name,sha256=digest,kind=kind,matches=matches))
report=dict(user_provided_labels={'marketing_model':'DC-S5','regulatory_model':'P2004A','radio_approval':'2020AP7120',
    'serial_masked':'*******2960','serial_sha256':hashlib.sha256(SERIAL.encode()).hexdigest()},
    no_serial_submitted_to_external_service=True,results=results,
    exact_serial_match=any(m['label']=='body_serial' for r in results for m in r['matches']),
    limitations=['Exact full-label ASCII/UTF16 search only; missing text does not establish different camera or absent identity.',
                 'A body label is not cryptographic key material without a proven firmware data-flow/KDF relation.'])
(OUT/'device_label_correlation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
