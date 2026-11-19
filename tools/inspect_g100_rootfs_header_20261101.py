"""Read only the verified G100 SquashFS superblocks; no mount/extraction/run."""
from pathlib import Path
import struct,hashlib,json
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'analysis/eeprom_keyhunt_20261101'
OUT=BASE/'official_oss_review/parent_review';OUT.mkdir(exist_ok=True)
container=json.loads((BASE/'g100_official/container.json').read_text(encoding='utf-8'))
fields=['magic','inodes','mkfs_time','block_size','fragments','compression','block_log','flags','ids','major','minor','root_inode','bytes_used','id_table_start','xattr_id_table_start','inode_table_start','directory_table_start','fragment_table_start','export_table_start']
rows=[]
for e in container['entries']:
    if e['name'] not in ('rootfs1','rootfs2'):continue
    b=(ROOT/e['section_file']).read_bytes();assert len(b)==e['size'] and hashlib.sha256(b).hexdigest()==e['directory_sha256']==e['payload_sha256']
    sb=dict(zip(fields,struct.unpack_from('<5I6H8Q',b)))
    assert sb['magic']==0x73717368 and sb['major']==4 and sb['minor']==0 and sb['bytes_used']<=len(b)
    assert (1<<sb['block_log'])==sb['block_size']
    rows.append(dict(section=e['name'],file=e['section_file'],section_sha256=hashlib.sha256(b).hexdigest(),section_size=len(b),superblock=sb,
        compression_name={1:'gzip',2:'lzma',3:'lzo',4:'xz',5:'lz4',6:'zstd'}.get(sb['compression'],'unknown'),filesystem_bytes_not_yet_extracted=True))
result=dict(scope='Already obtained official G100 raw sections, outer34=0. Header inspection only; not S5 decryption.',filesystems=rows,
    next_evidence='Rootfs files/scripts/native libraries are a separate code source from raw program and public Linux source; inspect statically with no mount or executable loading.',
    payload_decryption_key_recovered=False)
(OUT/'rootfs_superblocks.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
