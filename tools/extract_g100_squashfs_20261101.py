"""Bounded static SquashFS parsing. Never mount, follow symlinks, create devices,
execute extracted binaries or scripts. Outputs indexed ordinary data files only.
"""
from pathlib import Path
import sys,json,hashlib,io,struct,collections,time,importlib.metadata
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'analysis/eeprom_keyhunt_20261101'
sys.path.insert(0,str(BASE/'squashfs_tooling'))
from dissect.squashfs import SquashFS
OUT=BASE/'g100_rootfs_review';OUT.mkdir(exist_ok=True)
def sha(b):return hashlib.sha256(b).hexdigest()
class CheckedFS(SquashFS):
    def __init__(self,fh):
        self.blocks=[];super().__init__(fh)
    def _read_block(self,block,length=None):
        metadata=length is None
        assert 0<=block<self.size
        if metadata:
            assert block+2<=self.size
            self.fh.seek(block);head=self.fh.read(2);assert len(head)==2
            code=struct.unpack('<H',head)[0];n=code&0x7fff;compressed=not(code&0x8000);payload=block+2
            limit=8192
        else:
            assert 0<=length<0x2000000
            n=length&0xffffff;compressed=not(length&0x1000000);payload=block;limit=self.block_size
        assert 0<n<=limit and payload+n<=self.size
        self.fh.seek(payload);raw=self.fh.read(n);assert len(raw)==n
        decoded=self._compression.decompress(raw,limit) if compressed else raw
        assert 0<len(decoded)<=limit
        self.blocks.append(dict(offset=block,payload_offset=payload,metadata=metadata,compressed=compressed,stored_size=n,decoded_size=len(decoded),stored_sha256=sha(raw),decoded_sha256=sha(decoded)))
        return payload+n,decoded
    def _read_metadata(self,block,offset,length):
        assert 0<=length<=1024*1024 and 0<=offset<8192
        result=[];hops=0
        while length:
            nxt,data=self._read_block(block);assert 0<=offset<len(data)
            take=min(length,len(data)-offset);assert take>0
            result.append(data[offset:offset+take]);length-=take;offset+=take
            if offset==len(data):block=nxt;offset=0
            hops+=1;assert hops<=256
        return block,offset,b''.join(result)
def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():assert path.read_bytes()==data
    else:
        with path.open('xb') as f:f.write(data)
def main():
    started=time.monotonic();manifest=json.loads((BASE/'g100_official/container.json').read_text(encoding='utf-8'));allrows=[];summaries=[]
    for entry in manifest['entries']:
        if entry['name'] not in ('rootfs1','rootfs2'):continue
        image=(ROOT/entry['section_file']).read_bytes();assert len(image)==entry['size'] and sha(image)==entry['payload_sha256']==entry['directory_sha256']
        fs=CheckedFS(io.BytesIO(image));assert fs.sb.compression==3 and fs.major==4 and fs.minor==0 and fs.size<=len(image)
        rows=[];seen_dirs=set();inodes=set();total=0
        def walk(node,path,depth=0):
            nonlocal total
            assert depth<=32 and len(rows)<10000
            number=node.inode_number;assert number==node.header.inode_number and 1<=number<=fs.sb.inodes
            inodes.add(number)
            kind='dir' if node.is_dir() else 'file' if node.is_file() else 'symlink' if node.is_symlink() else 'special'
            row=dict(section=entry['name'],path=path,inode=number,kind=kind,mode=node.mode,size=node.size,uid=node.uid,gid=node.gid,metadata_block=node.block,metadata_offset=node.offset)
            rows.append(row)
            if kind=='dir':
                assert number not in seen_dirs;seen_dirs.add(number)
                names=set()
                for child in node.iterdir():
                    assert child.name not in ('','.','..') and '/' not in child.name and '\\' not in child.name and '\0' not in child.name
                    assert child.name not in names;names.add(child.name)
                    walk(child,path.rstrip('/')+'/'+child.name,depth+1)
            elif kind=='file':
                assert 0<=node.size<=64*1024*1024
                data=node.open().read(node.size+1);assert len(data)==node.size
                total+=len(data);assert total<=256*1024*1024
                digest=sha(data);dest=OUT/'objects'/(digest+'.bin');save(dest,data)
                row.update(sha256=digest,output_file=str(dest.relative_to(ROOT)),ELF=data.startswith(b'\x7fELF'))
                try:
                    text=data.decode('utf-8')
                    if b'\0' not in data and all(c.isprintable() or c in '\r\n\t' for c in text):
                        txt=OUT/'text'/(entry['name']+'_'+str(number)+'_'+Path(path).name.replace(':','_')+'.txt')
                        save(txt,data);row['text_file']=str(txt.relative_to(ROOT))
                except UnicodeDecodeError:pass
            elif kind=='symlink':row['target_recorded_only']=node.link
        walk(fs.root,'/')
        # Export-index independently reaches the same inode IDs/locations as directory traversal.
        export={n.inode_number:(n.block,n.offset) for n in fs.iter_inodes()}
        assert len(export)==fs.sb.inodes and set(export)==inodes
        for row in rows:assert export[row['inode']]==(row['metadata_block'],row['metadata_offset'])
        summary=dict(section=entry['name'],input_file=entry['section_file'],input_sha256=sha(image),flags=fs.flags,flags_interpretation='NOI(bit0),DUP(bit6),EXPORT(bit7); NO_FRAG/ALWAYS_FRAG unset',
            unique_inode_count=len(inodes),superblock_inode_count=fs.sb.inodes,export_directory_crosscheck_passed=True,entries=len(rows),types=dict(collections.Counter(r['kind'] for r in rows)),extracted_regular_file_bytes=total,blocks_read=len(fs.blocks))
        (OUT/(entry['name']+'_blocks.json')).write_text(json.dumps(fs.blocks,indent=2),encoding='utf-8')
        summaries.append(summary);allrows+=rows;print('ROOTFS_COMPLETE',json.dumps(summary),flush=True)
    result=dict(method='Dissect SquashFS with bounded reads and decoded-block limits; complete directory traversal plus independent export-index consistency; no mount, firmware execution, symlink/device creation.',
        parser_versions={n:importlib.metadata.version(n) for n in ('dissect.squashfs','dissect.cstruct','dissect.util')},summaries=summaries,entries=allrows,elapsed_seconds=time.monotonic()-started)
    (OUT/'rootfs_inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('ALL_COMPLETE',len(allrows),'seconds',result['elapsed_seconds'],flush=True)
if __name__=='__main__':main()
