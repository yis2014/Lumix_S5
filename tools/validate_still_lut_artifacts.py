"""Validate offline static-analysis artifacts, coordinates and unchanged original inputs."""
from pathlib import Path
import json,hashlib,csv,re,sys
sys.dont_write_bytecode=True
import compare_still_lut_containers as parser
R=Path(__file__).resolve().parent;D=R/'analysis'/'still_lut_port'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(8*1024*1024):h.update(b)
    return h.hexdigest()
def main():
    r=json.loads((D/'container_comparison.json').read_text(encoding='utf-8'));ind=json.loads((D/'s5m2_independent_evidence_20261030.json').read_text(encoding='utf-8'));c=json.loads((D/'candidate_data_paths.json').read_text(encoding='utf-8'));checks=[]
    assert parser.selftest()=='PASS';checks.append('parser synthetic/bounds/duplicate-name regression PASS')
    for x in r['inputs']:
        p=R/x['file'];assert p.stat().st_size==x['bytes'] and sha(p)==x['sha256'];assert x['crc_matches'];checks.append(x['file']+' original length/SHA unchanged and CRC validated')
    m=r['inputs'][2];assert m['sha256']==ind['input']['sha256'];assert len(m['entries'])==len(ind['partitions'])==58
    for x,y in zip(m['entries'],ind['partitions']):
        assert (x['index'],x['name'],x['file_offset'],x['size'],x['flags'],x['directory_digest32'],x['raw_sha256'],x['aux16'])==(y['index'],y['name'],y['file_range']['start'],y['size'],y['flags'],y['recorded_sha256'],y['actual_stored_bytes_sha256'],y['aux16'])
    checks.append('all 58 S5M2 entries agree with independent parser/hash report')
    for a in c['anchors']:
        x=next(e for im in r['inputs'] if im['file']==a['image'] for e in im['entries'] if e['name']==a['entry'])
        assert x['file_offset']==int(a['file_offset_hex'],16) and x['size']==a['bytes'] and x['directory_target_unmapped']==int(a['directory_target_hex'],16) and a['VA'] is None
    checks.append('all candidate file-offset/length/unmapped-target anchors match actual directory')
    with (D/'s5_v29_vs_s5m2_v37.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    assert len(rows)==24 and len({x['match_key'] for x in rows})==24;checks.append('cross-image CSV has 24 distinct comparison keys')
    doc=D/'S5与S5M2_静态照片LUT移植评估.md';links=re.findall(r'\]\(([^)]+)\)',doc.read_text(encoding='utf-8'))
    for link in links:
        if not link.startswith(('http:','https:','#')):assert (doc.parent/link.split('#',1)[0]).exists(),link
    checks.append('all report local links resolve')
    files=[p for p in D.iterdir() if p.is_file()]+[R/x for x in ['compare_still_lut_containers.py','test_still_lut_resource_envelope.py','validate_still_lut_artifacts.py']]
    out={'status':'PASS','scope':'artifact and container validation; NOT function recovery, decryption, QEMU or port success','checks':checks,'files':[{'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(files)]}
    with (D/'artifact_validation.json').open('x',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2)
    print(json.dumps({'status':out['status'],'checks':checks,'artifact_count':len(files)},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
