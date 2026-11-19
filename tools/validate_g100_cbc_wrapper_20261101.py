"""Bounded virtual ARM full-object ABI check, not a camera firmware run."""
from pathlib import Path
import json,hashlib,struct
import emulate_g100_crypto_20261101 as M
from unicorn.arm_const import UC_ARM_REG_R0
OUT=M.BASE/'emulated_crypto'
OBJ=M.DATA+0x10000;IVPTR=M.DATA+0x6000
records=[]
for label,key,iv,data in [
    ('synthetic-distinct-bytes',bytes(range(16)),bytes(range(16,32)),bytes(range(64))),
    ('G100-static-candidate-synthetic-ciphertext',bytes.fromhex('71143e939bc0784037dc4d3966de6d09'),bytes(16),hashlib.sha256(b'fixed-probe').digest()*2)]:
    emu=M.FirmwareCrypto();context=emu.setup(key,3)
    emu.uc.mem_write(OBJ,bytes(0x200));emu.uc.mem_write(M.KEY,key);emu.uc.mem_write(IVPTR,iv)
    sequence=[(0x3c3508,[OBJ]),(0x3c3592,[OBJ,128]),(0x3c3578,[OBJ,M.KEY]),(0x3c3558,[OBJ,1]),(0x3c3560,[OBJ,IVPTR]),(0x3c35e0,[OBJ])]
    for offset,args in sequence:emu.call(offset,args)
    actual_context=bytes(emu.uc.mem_read(OBJ+0x14,0x100))
    assert struct.unpack_from('<I',actual_context)[0]==5
    assert actual_context[0x28:0x28+96].hex()==context['round_keys']
    emu.uc.mem_write(M.INPUT,data);emu.uc.mem_write(M.OUTPUT,bytes(len(data)))
    emu.uc.mem_write(M.STACK,struct.pack('<I',len(data)))
    emu.call(0x3c3634,[OBJ,M.INPUT,len(data),M.OUTPUT])
    produced=emu.uc.reg_read(UC_ARM_REG_R0)
    output=bytes(emu.uc.mem_read(M.OUTPUT,len(data)))
    reference=M.cbc_decrypt(data,context,iv)
    assert output==reference and produced==len(data) and not emu.invalid
    records.append(dict(label=label,key_bytes_unchanged=True,context_rounds=5,full_wrapper_equals_minimal_primitive=True,
        produced=produced,input_bytes=len(data),output_sha256=hashlib.sha256(output).hexdigest()))
result=dict(scope='Virtual CPU wrapper ABI and key/IV data-flow control checks only; no real S5 decryption acceptance.',records=records,all_passed=True)
(OUT/'cbc_wrapper_validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
