"""Independent decoded-block cross-check using existing host LZO2 DLL.
The DLL is host tooling, not firmware. ARM objects are never loaded/executed.
"""
from pathlib import Path
import json,hashlib,ctypes,ctypes.util,re,collections
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'analysis/eeprom_keyhunt_20261101';OUT=BASE/'g100_rootfs_review'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    inventory=json.loads((OUT/'rootfs_inventory.json').read_text(encoding='utf-8'))
    library=Path(ctypes.util.find_library('lzo2')).resolve();digest=sha(library.read_bytes())
    dll=ctypes.CDLL(str(library));fn=dll.lzo1x_decompress_safe
    fn.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.c_void_p];fn.restype=ctypes.c_int
    controls=[]
    for summary in inventory['summaries']:
        image=(ROOT/summary['input_file']).read_bytes();assert sha(image)==summary['input_sha256']
        blocks=json.loads((OUT/(summary['section']+'_blocks.json')).read_text(encoding='utf-8'))
        counts=collections.Counter()
        for block in blocks:
            raw=image[block['payload_offset']:block['payload_offset']+block['stored_size']];assert sha(raw)==block['stored_sha256']
            if not block['compressed']:continue
            limit=8192 if block['metadata'] else 131072
            source=ctypes.create_string_buffer(raw);dest=ctypes.create_string_buffer(limit);size=ctypes.c_size_t(limit)
            rc=fn(source,len(raw),dest,ctypes.byref(size),None)
            assert rc==0 and size.value==block['decoded_size'] and sha(dest.raw[:size.value])==block['decoded_sha256']
            counts['metadata' if block['metadata'] else 'data']+=1
        controls.append(dict(section=summary['section'],independent_LZO2_matches=dict(counts),all_passed=True))
    stringrows=[];targets=[]
    pattern=re.compile(rb'(?i)firmware|update|/dev/(?:icc|icsm|mem)|/mnt/|/sd|\.plf|LENS-UPDATE|decrypt|AES_|keyslot|ioctl|common_spin|telnet|busybox|lighttpd|OpenSSL')
    seen={}
    for row in inventory['entries']:
        if row['kind']!='file':continue
        b=(ROOT/row['output_file']).read_bytes();assert sha(b)==row['sha256']
        if not row['ELF']:continue
        if row['sha256'] not in seen:
            extracted=[]
            for m in re.finditer(rb'[\x20-\x7e]{5,}',b):
                if pattern.search(m.group()):extracted.append(dict(offset=m.start(),text=m.group().decode('ascii')))
            seen[row['sha256']]=extracted
        matches=seen[row['sha256']]
        stringrows.append(dict(section=row['section'],path=row['path'],sha256=row['sha256'],source_file=row['output_file'],matches=matches))
        if matches:targets.append(dict(section=row['section'],path=row['path'],sha256=row['sha256'],matching_strings=len(matches)))
    result=dict(host_decoder_library=str(library),host_decoder_library_sha256=digest,independent_decoding_checks=controls,
        firmware_code_executed=False,filesystem_mounted=False,ELF_objects=len(stringrows),ELF_candidates=targets,
        limits='Strings are leads only; call-chain, reachable input and S5 applicability still require verification.')
    (OUT/'independent_lzo_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'ELF_target_strings.json').write_text(json.dumps(stringrows,ensure_ascii=False,indent=2),encoding='utf-8')
    print('INDEPENDENT_LZO_CHECKS',json.dumps(controls),flush=True)
    print('ELF_OBJECTS',len(stringrows),'STRING_CANDIDATES',len(targets),flush=True)
if __name__=='__main__':main()
