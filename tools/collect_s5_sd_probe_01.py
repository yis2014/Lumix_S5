"""Read only six known research files on returned test card; write captures only to workspace.
No filesystem repair, camera commands, unknown content extraction, or SD writes.
"""
from pathlib import Path
import json,hashlib,datetime
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'analysis/eeprom_keyhunt_20261101/s5_entry_review/sd_probe_01'
def sha(b):return hashlib.sha256(b).hexdigest()
def collect(card,output,manifest):
    expected=dict(manifest['after_original_hashes']);expected.update(manifest['verified_readback'])
    output.mkdir(parents=True,exist_ok=False)
    entries=[]
    for name,baseline in expected.items():
        path=card/name
        if not path.is_file():
            entries.append(dict(name=name,status='missing',expected_sha256=baseline));continue
        if path.stat().st_size>2*1024*1024:
            entries.append(dict(name=name,status='size_limit',expected_sha256=baseline));continue
        b=path.read_bytes();digest=sha(b)
        with (output/name).open('xb') as f:f.write(b)
        entries.append(dict(name=name,bytes=len(b),sha256=digest,expected_sha256=baseline,unchanged=digest==baseline,status='captured'))
    result=dict(captured_at=datetime.datetime.now().astimezone().isoformat(),source=str(card),files=entries,
        scope='Six fixed allowlisted files only; no SD writes, no repair, no camera commands. No recursive media/private file reading.',
        root_listing=[dict(name=p.name,is_directory=p.is_dir(),bytes=p.stat().st_size if p.is_file() else None) for p in sorted(card.iterdir(),key=lambda p:p.name)],
        interpretation='Unchanged input files do not prove whether camera parsed every LUT row or committed a slot; no camera error log or memory dump is implied.',
        key_recovered=False)
    (output/'capture.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
if __name__=='__main__':
    manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
    card=Path('H:/')
    if not card.is_dir():raise SystemExit('TEST_CARD_NOT_PRESENT; no capture performed')
    # Read-only identity sanity check; a missing/changed original means stop, not inspect another volume.
    if not (card/'vlog.vlt').is_file() or sha((card/'vlog.vlt').read_bytes())!=manifest['source_sha256']:
        raise SystemExit('CARD_BASELINE_MISMATCH; no capture performed')
    output=BASE/('returned_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    result=collect(card,output,manifest)
    print(json.dumps(dict(output=str(output.relative_to(ROOT)),files=result['files'],scope=result['scope']),ensure_ascii=False,indent=2))
