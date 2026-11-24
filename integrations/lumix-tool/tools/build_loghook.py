from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
import struct

asm = """
    push {r4-r7}
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
    pop {r4-r7}
    push.w {r3-r8, sb, sl, fp, lr}
    mov r5, r1
    mov r4, r0
    ldr.w pc, [pc, #0]
    .word 0x87F4C60B
"""
ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
enc, cnt = ks.asm(asm, 0x86370000)
data = bytes(enc)
open(r'out\prog_loghook2.bin','wb').write(data)
print('bytes', len(data), data.hex())
print('instrs', cnt)
# hook patch at 0x87F4C602
hook = bytes.fromhex('dff800f0') + struct.pack('<I', 0x86370001)
open(r'out\hook_log.bin','wb').write(hook)
print('hook', hook.hex())
