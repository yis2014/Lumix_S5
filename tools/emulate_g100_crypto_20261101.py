"""Bounded ARM emulation of actual G100 crypto functions + exact NumPy port.
Only isolated crypto functions run in a virtual CPU. No device/MMIO access,
firmware boot, native firmware execution, flashing, or input modifications.
"""
from pathlib import Path
import sys,struct,json,hashlib,time
import numpy as np
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'analysis/eeprom_keyhunt_20261101/g100_official'
OUT=BASE/'emulated_crypto';OUT.mkdir(exist_ok=True)
sys.path.insert(0,str(BASE/'tooling'))
import unicorn
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_HOOK_MEM_INVALID,UC_PROT_READ,UC_PROT_EXEC
from unicorn.arm_const import *
import key_research_20261101 as K
from eeprom_layout_delta_20261101 import layouts

PROGRAM=(BASE/'sections/03_program_0.bin').read_bytes()
CONTAINER=json.loads((BASE/'container.json').read_text(encoding='utf-8'))
PE=next(e for e in CONTAINER['entries'] if e['name']=='program')
assert K.sha(PROGRAM)==PE['payload_sha256']==PE['directory_sha256']
CODE=0x04a80000;DATA=0x10000000;CTX=DATA+0x1000;KEY=DATA+0x3000;INPUT=DATA+0x4000;OUTPUT=DATA+0x5000;STOP=DATA+0x80000;STACK=DATA+0xf0000

class FirmwareCrypto:
    def __init__(self):
        self.uc=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
        self.uc.mem_map(CODE,(len(PROGRAM)+4095)&~4095)
        self.uc.mem_write(CODE,PROGRAM)
        self.uc.mem_protect(CODE,(len(PROGRAM)+4095)&~4095,UC_PROT_READ|UC_PROT_EXEC)
        self.uc.mem_map(DATA,0x100000)
        self.invalid=[]
        self.uc.hook_add(UC_HOOK_MEM_INVALID,self.bad_memory)
    def bad_memory(self,uc,access,address,size,value,user):
        self.invalid.append(dict(access=access,address=hex(address),size=size))
        return False
    def call(self,offset,args):
        for reg in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12):self.uc.reg_write(reg,0)
        for reg,val in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):self.uc.reg_write(reg,val)
        self.uc.reg_write(UC_ARM_REG_SP,STACK);self.uc.reg_write(UC_ARM_REG_LR,STOP|1)
        self.uc.emu_start((CODE+offset)|1,STOP,timeout=2000000,count=200000)
        if self.uc.reg_read(UC_ARM_REG_PC)!=STOP:raise RuntimeError('Bounded emulation did not return: '+hex(offset))
    def setup(self,key,kind):
        self.uc.mem_write(CTX,bytes(2048));self.uc.mem_write(KEY,key)
        self.call(0x47032e if kind==2 else 0x4703ee,[CTX,KEY,len(key)])
        nr,nk=struct.unpack('<2I',self.uc.mem_read(CTX,8))
        context=bytes(self.uc.mem_read(CTX,2048))
        return dict(kind=kind,rounds=nr,nk=nk,round_keys=context[0x28:0x28+16*(nr+1)].hex(),context=context.hex())
    def decrypt_block(self,block):
        assert len(block)==16
        self.uc.mem_write(INPUT,block);self.uc.mem_write(OUTPUT,bytes(16))
        self.call(0x47036a,[CTX,INPUT,OUTPUT])
        return bytes(self.uc.mem_read(OUTPUT,16))

# Exact table/word semantics transcribed from program+46FFFE and final loop.
TBASE=0x0524b390-CODE
TD=[np.frombuffer(PROGRAM[TBASE+0x400*i:TBASE+0x400*(i+1)],dtype='<u4').copy() for i in range(4)]
IS=np.frombuffer(PROGRAM[0x0524a290-CODE:0x0524a290-CODE+256],dtype=np.uint8).astype(np.uint32)

def decrypt_blocks(data,context):
    assert len(data)%16==0
    nr=context['rounds'];rk=np.frombuffer(bytes.fromhex(context['round_keys']),dtype='<u4').reshape(nr+1,4)
    s=np.frombuffer(data,dtype='<u4').reshape(-1,4).copy()^rk[0]
    for r in range(1,nr):
        new=np.empty_like(s)
        for c in range(4):new[:,c]=TD[0][s[:,c]&255]^TD[1][(s[:,(c+3)%4]>>8)&255]^TD[2][(s[:,(c+2)%4]>>16)&255]^TD[3][s[:,(c+1)%4]>>24]^rk[r,c]
        s=new
    new=np.empty_like(s)
    for c in range(4):new[:,c]=IS[s[:,c]&255]^(IS[(s[:,(c+3)%4]>>8)&255]<<8)^(IS[(s[:,(c+2)%4]>>16)&255]<<16)^(IS[s[:,(c+1)%4]>>24]<<24)^rk[nr,c]
    return new.astype('<u4',copy=False).tobytes()

def cbc_decrypt(data,context,iv):
    assert len(iv)==16 and len(data)%16==0
    out=[];previous=iv
    for start in range(0,len(data),1024*1024):
        chunk=data[start:start+1024*1024]
        dec=decrypt_blocks(chunk,context)
        chained=previous+chunk[:-16]
        plain=np.bitwise_xor(np.frombuffer(dec,dtype=np.uint8),np.frombuffer(chained,dtype=np.uint8)).tobytes()
        out.append(plain);previous=chunk[-16:]
    return b''.join(out)

def main():
    began=time.monotonic();emu=FirmwareCrypto();selftests=[]
    standard_key=bytes(range(16));p=bytes.fromhex('00112233445566778899aabbccddeeff');c=bytes.fromhex('69c4e0d86a7b0430d8cdb78070b4c55a')
    context=emu.setup(standard_key,2)
    assert context['rounds']==10 and emu.decrypt_block(c)==p and decrypt_blocks(c,context)==p
    selftests.append(dict(test='Actual G100 outer2 primitive vs FIPS197 AES128 ECB',passed=True))
    for kind in (2,3):
        ctx=emu.setup(standard_key,kind)
        vectors=b''.join(hashlib.sha256(('deterministic-block-'+str(i)).encode()).digest()[:16] for i in range(64))
        actual=b''.join(emu.decrypt_block(vectors[i:i+16]) for i in range(0,len(vectors),16))
        assert decrypt_blocks(vectors,ctx)==actual
        assert len(set(actual))>32
        selftests.append(dict(test='NumPy exact port vs actual bounded ARM code',kind=kind,rounds=ctx['rounds'],independent_blocks=64,passed=True))
    assert not emu.invalid
    print('EMU_AND_PORT_SELFTESTS_PASS',json.dumps(selftests),flush=True)
    key_record=json.loads((BASE/'update_review/key_candidate_scatter.json').read_text(encoding='utf-8'))
    key=bytes.fromhex(key_record['bytes']);assert PROGRAM[0x8fe2b8:0x8fe2b8+16]==key
    manifest=json.loads((ROOT/'analysis/verification_20261101/verification.json').read_text(encoding='utf-8'))
    images={n:(ROOT/n).read_bytes() for n in manifest['images']}
    for name,data in images.items():assert K.sha(data)==manifest['images'][name]['sha256']
    targets=[]
    for label in ('eep_act_a','eep_act_b','ipu_data','koutei_kao','music'):
        plain=(ROOT/'analysis/william_review/plaintext_samples'/('rec_S5V29_'+label+'_from_G100.bin')).read_bytes()
        for name,m in manifest['images'].items():
            for e in m['partitions']:
                if e['name']==label and e['size']==len(plain) and e['stored_digest']==K.sha(plain) and e['flags']==3:
                    targets.append((name,e,plain))
    assert len(targets)==11
    keys={}
    for label,k in layouts(key):keys.setdefault(k,label)
    checks=[];verified_keys={};verified_resources=[]
    for candidate,transform in keys.items():
        context=emu.setup(candidate,3)
        for name,e,expected in targets:
            ct=images[name][e['file_offset']:e['end']];iv=bytes.fromhex(e['aux16'])
            first32=cbc_decrypt(ct[:32],context,iv)
            success=False
            if first32==expected[:32]:
                plain=cbc_decrypt(ct,context,iv)
                success=(len(plain)==len(expected) and K.sha(plain)==e['stored_digest'] and plain==expected)
                if success:
                    verified_keys[candidate]=context
                    verified_resources.append(dict(image=name,partition=e['name'],key_hex=candidate.hex(),key_transform=transform,
                        size=len(plain),sha256=K.sha(plain),iv=iv.hex(),complete_bytes_equal_known_plaintext=True))
                    print('VERIFIED_RESOURCE',name,e['name'],len(plain),K.sha(plain),flush=True)
            checks.append(dict(image=name,partition=e['name'],transform=transform,first32_matches=first32==expected[:32],full_verified=success))
    partition_checks=[];programs=[]
    for candidate,context in verified_keys.items():
        for name,m in manifest['images'].items():
            image=images[name]
            for e in m['partitions']:
                if e['flags']!=3:continue
                ct=image[e['file_offset']:e['end']]
                plain=cbc_decrypt(ct,context,bytes.fromhex(e['aux16']))
                digest=K.sha(plain);good=digest==e['stored_digest'] and len(plain)==e['size']
                row=dict(image=name,partition=e['name'],index=e['index'] if 'index' in e else None,key_hex=candidate.hex(),
                    plaintext_bytes=len(plain),expected_sha256=e['stored_digest'],output_sha256=digest,full_sha256_matches=good)
                if good and e['name']=='program':
                    dest=OUT/(Path(name).stem+'_program_verified.bin')
                    if dest.exists():assert dest.read_bytes()==plain
                    else:
                        with dest.open('xb') as f:f.write(plain)
                    row['verified_output']=str(dest.relative_to(ROOT));programs.append(row)
                partition_checks.append(row)
            print('IMAGE_COMPLETE',name,'verified',sum(r['full_sha256_matches'] for r in partition_checks if r['image']==name),flush=True)
    result=dict(official_g100_sha256=CONTAINER['sha256'],unicorn_version=unicorn.__version__,
        emulation_scope='Only bounded crypto keysetup/block functions in virtual ARM; read-only code and mapped scratch memory; invalid-memory hook stops; no camera or firmware boot.',
        selftests=selftests,invalid_memory_accesses=emu.invalid,source_key_candidate=key_record,
        tested_key_layouts=len(keys),known_resource_checks=checks,verified_known_resources=verified_resources,
        verified_keys_hex=[k.hex() for k in verified_keys],full_partition_checks=partition_checks,verified_programs=programs,
        key_recovered=bool(verified_keys and programs),elapsed_seconds=time.monotonic()-began,
        acceptance='Known plaintext full length/SHA/bytes plus complete firmware program directory SHA; no prefix-only success.')
    (OUT/'emulated_crypto_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    if result['key_recovered']:
        (OUT/'verified_firmware_keys.json').write_text(json.dumps(dict(keys=result['verified_keys_hex'],scheme='G100 encoding3 primitive, CBC; AES128 key schedule with Nr=5',partition_iv='directory entry+0x3C aux16',verified_resources=len(verified_resources),verified_programs=programs),ensure_ascii=False,indent=2),encoding='utf-8')
    print('FINAL',json.dumps({k:result[k] for k in ['verified_keys_hex','key_recovered','elapsed_seconds']}),flush=True)
if __name__=='__main__':main()
