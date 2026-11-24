from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
import struct

RET = 0x864D4415   # original dispatcher body (thumb)
asm = f"""
    push {{r4-r7}}
    mov r4, r0
    mov r5, r1
    mov r6, r2
    mov r7, r3
    movw r3, #0x2000
    movt r3, #0x8F30
    ldr r2, [r3]
    cmp r2, #64
    bhs skip
    adds r2, #1
    str r2, [r3]
    subs r2, #1
    lsls r2, r2, #4
    movw r0, #0x2100
    movt r0, #0x8F30
    add r0, r0, r2
    str r4, [r0]
    str r5, [r0, #4]
    str r6, [r0, #8]
    str r7, [r0, #12]
skip:
    pop {{r4-r7}}
    ldr.w pc, [pc, #0]
    .word {hex(RET)}
"""
ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
enc, cnt = ks.asm(asm, 0x86370000)
data = bytes(enc)
open(r'out\prog_selftest.bin','wb').write(data)
print('bytes', len(data), data.hex())

def enc_bw(addr, target):
    off = target - (addr + 4)
    if off < 0: off += 1 << 25
    s=(off>>24)&1; i1=(off>>23)&1; i2=(off>>22)&1
    imm10=(off>>12)&0x3FF; imm11=(off>>1)&0x7FF
    j1=1-(i1^s); j2=1-(i2^s)
    hw1=0xF000|(s<<10)|imm10
    hw2=0x8000|(j1<<13)|0x1000|(j2<<11)|imm11
    return struct.pack('<HH', hw1, hw2)
patch = enc_bw(0x868E59A0, 0x86370000)
open(r'out\selftest_patch.bin','wb').write(patch)
print('stub patch', patch.hex())
