"""S5 visual provenance controls. All channels within0..4095. No executable code.
Three fixed VLT files; --deploy exclusive-creates only these on previously bound testcard.
"""
from pathlib import Path
import json,hashlib,re,os,datetime,sys
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'analysis/eeprom_keyhunt_20261101/s5_entry_review'
OUT=BASE/'sd_probe_02';OUT.mkdir(exist_ok=True)
def sha(b):return hashlib.sha256(b).hexdigest()
def create(p,b):
    with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    assert p.read_bytes()==b
m1=json.loads((BASE/'sd_probe_01/manifest.json').read_text(encoding='utf-8'))
source=(ROOT/m1['source_file']).read_bytes();assert sha(source)==m1['source_sha256']
lines=source.splitlines(keepends=True);first=next(i for i,line in enumerate(lines) if re.fullmatch(rb'\s*\d+\s+\d+\s+\d+\s*',line))
prefix=b''.join(lines[:first]);newline=b'\r\n' if b'\r\n' in source else b'\n'
green=b'0 4095 0'+newline;magenta=b'4095 0 4095'+newline
files={'S5GREEN.VLT':prefix+green*4913,'S5MAG.VLT':prefix+magenta*4913,'S5MSHORT.VLT':prefix+magenta*4912}
assert files['S5MSHORT.VLT']==files['S5MAG.VLT'][:-len(magenta)]
rows=[]
for name,data in files.items():
    assert len(Path(name).stem)<=8
    triples=[tuple(map(int,line.split())) for line in data.splitlines() if re.fullmatch(rb'\s*\d+\s+\d+\s+\d+\s*',line)]
    assert len(triples)==(4912 if name=='S5MSHORT.VLT' else 4913)
    assert all(0<=v<=4095 for row in triples for v in row)
    p=OUT/name
    if p.exists():assert p.read_bytes()==data
    else:create(p,data)
    rows.append(dict(name=name,bytes=len(data),sha256=sha(data),records=len(triples),rgb=list(triples[0])))
result=dict(test_id='S5_SD_VLT_VISUAL_PROVENANCE_02',created_at=datetime.datetime.now().astimezone().isoformat(),stage='workspace_only',
    purpose='Distinguish new partial-file contents actually applied from prior LUT slot retention; not an out-of-bounds/leak/code-execution/key test.',
    files=rows,probe_diff='S5MSHORT is exact S5MAG minus final RGB record; complete green is distinguishable reset control.',
    expected_visuals=dict(S5GREEN='Uniform green when this LUT is actually applied.',S5MAG='Uniform magenta when this LUT is actually applied.',S5MSHORT='Unknown until tested; observe whether previously green view becomes magenta.'),
    steps=['Use same unused user LUT slot as prior test, no firmware-update or service menu.',
        'Import/apply S5GREEN: confirm green.',
        'Import/apply complete S5MAG: confirm magenta. Stop if either complete control fails or no distinct preview effect.',
        'Import/apply S5GREEN again: confirm green immediately before shortened sample.',
        'Import/apply S5MSHORT once: record exact import message and resulting color. Do not infer key leakage from a color.',
        'Restore original normal LUT selection and view-assist state after observations. LUT file deletion alone does not restore a modified user slot.'],
    side_effect='Deliberately uniform preview colors; may affect LUT-assisted HDMI preview if enabled. Not a sensor/firmware modification. Avoid recording test-preview output as real footage.',
    decision='If short imports and changes green→magenta without abnormal behavior, supported result is partial LUT content accepted; stop row-count branch absent further evidence.',
    key_export_capability=False,camera_executed=False)
if '--deploy' in sys.argv:
    card=Path('H:/');expected=dict(m1['after_original_hashes']);expected.update(m1['verified_readback'])
    before={n:sha((card/n).read_bytes()) for n in expected};assert before==expected,'CARD_OR_BASELINE_MISMATCH'
    for n in files:assert not (card/n).exists(),'TARGET_EXISTS: '+n
    for n,b in files.items():create(card/n,b)
    after={n:sha((card/n).read_bytes()) for n in expected};assert before==after
    result.update(stage='deployed',card_root=str(card),six_prior_hashes_unchanged=True,readback_sha256={n:sha((card/n).read_bytes()) for n in files})
(OUT/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
