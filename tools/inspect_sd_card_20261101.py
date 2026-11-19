"""Read a fixed allowlist of SD research files; write only under workspace.
No card writes, device access, volume repair, or image/media-content inspection.
"""
from pathlib import Path
import hashlib, re, json, struct, collections, math
import key_research_20261101 as kr

ROOT=Path(__file__).resolve().parent
CARD=Path('H:/')
OUT=ROOT/'analysis'/'sd_card_20261101'
ORIG=OUT/'originals';DER=OUT/'derived'
ORIG.mkdir(parents=True,exist_ok=True);DER.mkdir(exist_ok=True)
PREFIX='PRIVATE/PANA_GRP/PAVC/LUMIX/'
PATHS=['S5A.TXT','S5F.TXT','S5U.TXT','vlog.vlt',
       PREFIX+'CONTENTS.B00',PREFIX+'CONTENTS.D00',PREFIX+'FILEINFO.TBL',
       PREFIX+'GROUPINF.B00',PREFIX+'GROUPINF.D00',
       PREFIX+'TEMP/0d71ade0.CPC',PREFIX+'TEMP/0d71ade0.CPG',
       'DCIM/107_PANA/mp4_map.json']

def sha(b):return hashlib.sha256(b).hexdigest()
def entropy(b):
    c=collections.Counter(b);n=len(b)
    return -sum(v/n*math.log2(v/n) for v in c.values()) if n else 0

def main():
    records=[];blobs={};eeprom=[];schedules=[]
    for relative in PATHS:
        source=CARD/relative
        with source.open('rb') as f:
            b=f.read(8*1024*1024+1)
        if len(b)>8*1024*1024:raise ValueError('Unexpected file size')
        target=ORIG/relative;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if target.read_bytes()!=b:raise ValueError('Existing backup differs')
        else:
            with target.open('xb') as f:f.write(b)
        assert sha(target.read_bytes())==sha(b)
        blobs[relative]=b
        record=dict(source=str(source),backup=str(target.relative_to(ROOT)),size=len(b),sha256=sha(b),
                    entropy=entropy(b),head32_hex=b[:32].hex(),mtime_ns=source.stat().st_mtime_ns)
        records.append(record)
        if relative in ['S5A.TXT','S5F.TXT','S5U.TXT']:
            text=b.decode('ascii');words=[];addresses=[]
            for line in text.splitlines():
                if not line.startswith('H'):continue
                m=re.fullmatch(r'H([0-9a-fA-F]{3})\s+((?:[0-9a-fA-F]{4},){16})\s*',line)
                if not m:raise ValueError('Malformed EEPROM row')
                addresses.append(int(m[1],16));words.extend(int(s,16) for s in m[2].split(',') if s)
            assert addresses==list(range(4096)) and len(words)==65536
            area=re.search(r'AREA\s*:\s*([^\r\n]+)',text)[1].strip()
            variants=[]
            for endian,fmt in [('BE','>'),('LE','<')]:
                binary=struct.pack(fmt+'65536H',*words)
                name=relative[:-4]+'_words_'+endian+'.bin';p=DER/name
                if p.exists():assert p.read_bytes()==binary
                else:p.write_bytes(binary)
                row=dict(layout=endian,file=str(p.relative_to(ROOT)),bytes=len(binary),sha256=sha(binary),entropy=entropy(binary),
                    max_512byte_entropy=max(entropy(binary[i:i+512]) for i in range(0,len(binary),512)))
                variants.append(row)
                schedules.append(kr.scan_schedules(binary,'EEPROM:'+relative+':'+endian))
            eeprom.append(dict(source=str(source),area_label=area,header_data_size_text='0x10000',
                row_count=len(addresses),words=len(words),bytes_per_word=2,
                nonzero_words=sum(w!=0 for w in words),nonzero_nonffff_words=sum(w not in [0,65535] for w in words),
                variants=variants,
                interpretation='Text contains 65536 displayed u16 values; each explicit byte-order rendering is 131072 bytes. Header size units/runtime address mapping not established. No claim of code or key.'))
        elif relative.startswith(PREFIX):
            schedules.append(kr.scan_schedules(b,'SD:'+relative))
    lut=blobs['vlog.vlt'];rows=[]
    for line in lut.decode('utf-8-sig').splitlines():
        if re.fullmatch(r'\s*\d+\s+\d+\s+\d+\s*',line):rows.append(list(map(int,line.split())))
    equivalent=[]
    for i,(n,b) in enumerate(blobs.items()):
        for nn,bb in list(blobs.items())[i+1:]:
            if b==bb:equivalent.append([n,nn])
    # References only; no photo/video pixels or full original content in report.
    refs={}
    for n in PATHS:
        if n.startswith(PREFIX):
            b=blobs[n]
            refs[n]=[dict(offset=m.start(),name=m.group().decode('ascii')) for m in re.finditer(rb'(?:P\d{7}|\d{3}_PANA|LUMIX|Panasonic|[A-Za-z0-9_]{1,24}\.(?:JPG|RW2|MOV|MP4|VLT|CPC|CPG))',b,re.I)][:40]
    result=dict(scope='Fixed-allowlist SD file inspection; source opened rb only. No card writes or raw/deleted-space scan.',
        source_drive='H:',files=records,eeprom=eeprom,fully_matching_file_pairs=equivalent,
        standard_aes_schedule_scan=schedules,key_recovered=False,
        key_search_performed=False,
        key_statement='No full standard forward AES schedule found if all schedule arrays are empty; no direct EEPROM candidate key validation performed.',
        lut=dict(rows=len(rows),expected_17_cubed=4913,sha256=sha(lut),
                 matches_workspace_vlog=sha(lut)==sha((ROOT/'vlog.vlt').read_bytes())),
        metadata_filename_references=refs,
        limitations=['EEPROM export headings are file claims; live camera provenance and creation procedure not verified.',
                    'No signature algorithm, key location, record semantic or runtime address inferred from filenames.',
                    'No reverse-round/InvMixColumns/split schedule coverage.',
                    'No filesystem repair, raw sectors, deleted files or unallocated space inspected.',
                    'No photo/video pixels inspected.'])
    (OUT/'inventory_and_eeprom.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('FILES',json.dumps([dict(source=r['source'],size=r['size'],sha256=r['sha256'],entropy=round(r['entropy'],4)) for r in records],ensure_ascii=False))
    print('EEPROM',json.dumps(eeprom,ensure_ascii=False))
    print('IDENTICAL',equivalent)
    print('SCHEDULE_MATCHES',sum(len(r['fully_valid_schedules']) for r in schedules))
    print('LUT',result['lut'])
if __name__=='__main__':main()
