"""S5 SD input probe 01: known-size VLT control vs exactly one missing data row.
No firmware image, executable, shell script, filesystem corruption or key-export claim.
Default stages only in workspace; --deploy writes exactly two new root files on H:,
only after binding H: to the previously hashed VLT + EEPROM files. Never overwrites.
"""
from pathlib import Path
import hashlib,json,re,sys,os,datetime
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'analysis/eeprom_keyhunt_20261101/s5_entry_review'
OUT=BASE/'sd_probe_01';OUT.mkdir(exist_ok=True)
EXPECTED={
    'vlog.vlt':'ea94c9ca24512cac2e4715f7214b05fe3e528e5602ced52105ed495570f737f6',
    'S5A.TXT':'5080c9143f490b3b2cdf15fa7d990d0a6218e97505fefa5d3085580bd555702f',
    'S5F.TXT':'593143338f9b0341986607bfeec82ef2873e0a55c297488945c25e74bf321f01',
    'S5U.TXT':'5ab10aaf956376a2b1a7d0f1eda402a565c00135b79522c5d90cca51ab3f533b'}
def sha(b):return hashlib.sha256(b).hexdigest()
def exclusive(path,data):
    with path.open('xb') as f:
        f.write(data);f.flush();os.fsync(f.fileno())
    assert path.read_bytes()==data
src=ROOT/'analysis/sd_card_20261101/originals/vlog.vlt'
b=src.read_bytes();assert sha(b)==EXPECTED['vlog.vlt']
lines=b.splitlines(keepends=True)
assert lines[0].strip()==b'# panasonic vlt file version 1.0'
assert sum(x.strip()==b'LUT_3D_SIZE 17' for x in lines)==1
indexes=[i for i,x in enumerate(lines) if re.fullmatch(rb'\s*\d+\s+\d+\s+\d+\s*',x)]
assert len(indexes)==17**3
assert all(0<=int(v)<=4095 for i in indexes for v in lines[i].split())
assert not b''.join(lines[indexes[-1]+1:]).strip()
short=b''.join(x for i,x in enumerate(lines) if i!=indexes[-1])
assert len(short.splitlines())==len(b.splitlines())-1
assert short==b[:sum(map(len,lines[:indexes[-1]]))]+b''.join(lines[indexes[-1]+1:])
files={'S5BASE.VLT':b,'S5SHORT.VLT':short}
for name,data in files.items():
    dest=OUT/name
    if dest.exists():assert dest.read_bytes()==data
    else:exclusive(dest,data)
manifest=dict(test_id='S5_SD_VLT_ROWCOUNT_01',created_at=datetime.datetime.now().astimezone().isoformat(),
    target_model='DC-S5',method='Control is exact existing VLT bytes; one-variable probe removes only last RGB data row. Declared size remains17.',
    input_evidence='Existing card VLT and prior S5 VLT load observations; no G100 code used.',
    stage='workspace_only',source_file=str(src.relative_to(ROOT)),source_sha256=sha(b),
    files=[dict(name=n,bytes=len(v),sha256=sha(v),declared_edge=17,actual_records=4913 if n=='S5BASE.VLT' else 4912) for n,v in files.items()],
    removed_line_1based=indexes[-1]+1,removed_line_bytes=len(lines[indexes[-1]]),
    expected_observations=dict(control='Listed and imports normally if current S5 mode/card/LUT slot support it.',probe='A specific format/load error is expected from a row-count validating parser; actual response unknown until user tests.'),
    key_export_capability=False,code_execution_payload=False,camera_execution_performed=False,
    side_effects='User-triggered LUT import may replace the selected LUT slot or viewing transform. Use a confirmed unused user slot; changing files back does not restore a slot already overwritten. Parser robustness is not established; stop after first abnormal behavior.',
    instructions=['Eject card normally after host writes; camera powered off during card insertion.',
        'Use normal V-Log View Assist LUT Read/Load menu and an unused user slot. Do not open firmware-update/service/EEPROM-write menus.',
        'Record firmware version, slot, current LUT choice. Try S5BASE first and record exact result. If control fails, stop: do not test S5SHORT.',
        'If control succeeds, try S5SHORT once in that same unused test slot. Record exact error/success/response time and any abnormal behavior.',
        'No automatic reruns or forced power interruption during an operation. On abnormal behavior stop further inputs; do not proceed to updates.',
        'Return the card and observations for read-only before/after comparison. Do not treat import success, crash or a blank file as key recovery.'],
    cleanup='Only the two named new test files are candidates for later removal; no automatic cleanup is executed. Preserve original vlog.vlt and EEPROM dumps.')
if '--deploy' in sys.argv:
    card=Path('H:/')
    before={n:sha((card/n).read_bytes()) for n in EXPECTED};assert before==EXPECTED,'CARD_BINDING_MISMATCH'
    for name in files:assert not (card/name).exists(),'TARGET_ALREADY_EXISTS: '+name
    for name,data in files.items():exclusive(card/name,data)
    after={n:sha((card/n).read_bytes()) for n in EXPECTED};assert after==before
    manifest.update(stage='deployed',card_root=str(card),before_original_hashes=before,after_original_hashes=after,
        verified_readback={n:sha((card/n).read_bytes()) for n in files})
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False,indent=2))
