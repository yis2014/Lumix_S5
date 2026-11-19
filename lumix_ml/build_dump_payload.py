"""Functional payload on the proven lens-validator detour (0x868C5E48).

Besides counting invocations, the hook dumps the validator's calling context:
  BUF+0x00 : r0,r1,r2,r3,sp,lr (lr reveals the caller)
  BUF+0x40 : 0x40 bytes pointed to by r0 (likely the StcStream/this object)
  BUF+0x80 : 0x40 bytes pointed to by r1
If r0 is a C++ object, its first dword is the vtable pointer, whose entries are
the class's virtual methods (verify/read/write...) - the fastest route to the
signature-verify and Flash-read function addresses.

Self-test (keystone + unicorn) by default; --write deploys to the camera.
"""
import re
import struct
import sys

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_R4, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP,
)

from inject_test import bw

TARGET = 0x868C5E48
ORIG = bytes.fromhex("2de9ff4f")
RESUME = TARGET + 4
CAVE = 0x87086300
COUNTER = 0x87086450
BUF = 0x87086400
EXPECTED_PATCH = bytes.fromhex("c0f35ab2")  # b.w TARGET -> CAVE (unchanged)
BK_DIR = r"E:\desktop\LUMIX"

ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)

HOOK_ASM = f"""
    push {{r0-r4}}
    movw r4, #{BUF & 0xFFFF}
    movt r4, #{BUF >> 16}
    str r0, [r4, #0]
    str r1, [r4, #4]
    str r2, [r4, #8]
    str r3, [r4, #12]
    add r2, sp, #0
    str r2, [r4, #16]
    str.w lr, [r4, #20]
    movw r2, #{COUNTER & 0xFFFF}
    movt r2, #{COUNTER >> 16}
    ldr r3, [r2]
    adds r3, #1
    str r3, [r2]
    lsrs r2, r0, #24
    cmp r2, #0x06
    blo {{skip0}}
    cmp r2, #0x0b
    bhs {{skip0}}
    ldr r2, [r0]
    str r2, [r4, #0x20]
    ldr r2, [r0, #4]
    str r2, [r4, #0x24]
    ldr r2, [r0, #8]
    str r2, [r4, #0x28]
    ldr r2, [r0, #12]
    str r2, [r4, #0x2c]
skip0:
    lsrs r2, r1, #24
    cmp r2, #0x06
    blo {{skip1}}
    cmp r2, #0x0b
    bhs {{skip1}}
    ldr r2, [r1]
    str r2, [r4, #0x30]
    ldr r2, [r1, #4]
    str r2, [r4, #0x34]
    ldr r2, [r1, #8]
    str r2, [r4, #0x38]
    ldr r2, [r1, #12]
    str r2, [r4, #0x3c]
skip1:
    ldr r2, [r4, #8]
    lsrs r3, r2, #24
    cmp r3, #0x06
    blo {{skip2}}
    cmp r3, #0x0b
    bhs {{skip2}}
    ldr r3, [r2]
    str r3, [r4, #0x40]
    ldr r3, [r2, #4]
    str r3, [r4, #0x44]
    ldr r3, [r2, #8]
    str r3, [r4, #0x48]
    ldr r3, [r2, #12]
    str r3, [r4, #0x4c]
skip2:
    pop {{r0-r4}}
"""


def assemble(lines, base):
    def sub(text, mapping, fallback):
        return re.sub(r"\{(\w+)\}", lambda m: hex(mapping.get(m.group(1), fallback)), text)

    addr = base
    labels = {}
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if ln.endswith(":"):
            labels[ln[:-1]] = addr
            continue
        code = ks.asm(sub(ln, {}, addr), addr)[0]
        addr += len(code)
    out = bytearray()
    addr = base
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.endswith(":"):
            continue
        code = ks.asm(sub(ln, labels, addr), addr)[0]
        out += bytes(code)
        addr += len(code)
    return bytes(out)


def build_hook():
    body = assemble(HOOK_ASM.splitlines(), CAVE)
    code = body + ORIG
    code += bw(CAVE + len(code), RESUME)
    return code


def selftest(hook):
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    print(f"--- hook {len(hook)} bytes ---")
    for ins in md.disasm(hook, CAVE):
        print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")

    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    mu.mem_map(0x87080000, 0x20000)   # cave + buf
    mu.mem_map(0x09000000, 0x10000)   # objects (physical RAM)
    mu.mem_map(0x868C5000, 0x10000)   # target
    mu.mem_map(0x80000000, 0x10000)   # stack + return
    mu.mem_write(CAVE, hook)
    mu.mem_write(TARGET, bw(TARGET, CAVE))
    mu.mem_write(RESUME, struct.pack("<H", 0x4770))
    mu.mem_write(COUNTER, b"\x00" * 4)
    mu.mem_write(BUF, b"\x00" * 0x100)
    OBJ0 = 0x09000000
    OBJ1 = 0x09000100
    OBJ2 = 0x09000200
    mu.mem_write(OBJ0, bytes(range(0x40)))
    mu.mem_write(OBJ1, bytes(range(0x40, 0x80)))
    mu.mem_write(OBJ2, bytes(range(0x80, 0xC0)))
    ret = 0x80001000
    mu.mem_write(ret, struct.pack("<H", 0x4770))
    mu.reg_write(UC_ARM_REG_R0, OBJ0)
    mu.reg_write(UC_ARM_REG_R1, OBJ1)
    mu.reg_write(UC_ARM_REG_R2, OBJ2)
    mu.reg_write(UC_ARM_REG_R3, 0x44444444)
    mu.reg_write(UC_ARM_REG_LR, ret | 1)
    mu.reg_write(UC_ARM_REG_SP, 0x80008000)
    mu.reg_write(UC_ARM_REG_PC, TARGET | 1)
    mu.emu_start(TARGET | 1, ret, count=200)

    cnt = struct.unpack("<I", mu.mem_read(COUNTER, 4))[0]
    dump = bytes(mu.mem_read(BUF, 0x100))
    regs = struct.unpack_from("<6I", dump, 0)
    obj0 = dump[0x20:0x30]
    obj1 = dump[0x30:0x40]
    obj2 = dump[0x40:0x50]
    print(f"counter={cnt}, saved regs={[hex(r) for r in regs]}")
    print(f"r0 obj[:8]={obj0[:8].hex()}  r1 obj[:8]={obj1[:8].hex()}  r2 obj[:8]={obj2[:8].hex()}")
    assert cnt == 1
    assert regs[0] == OBJ0 and regs[1] == OBJ1 and regs[2] == OBJ2 and regs[3] == 0x44444444
    assert regs[5] == (ret | 1)
    assert obj0 == bytes(range(0x10)), "r0 object dump mismatch"
    assert obj1 == bytes(range(0x40, 0x50)), "r1 object dump mismatch"
    assert obj2 == bytes(range(0x80, 0x90)), "r2 object dump mismatch"
    after = [mu.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
    assert after == [OBJ0, OBJ1, OBJ2, 0x44444444], "argument registers not restored"
    print("SELFTEST PASS: counter, reg dump, both object dumps, registers restored")


def main():
    hook = build_hook()
    print(f"hook {len(hook)} bytes @ {CAVE:#x}, counter @ {COUNTER:#x}, buf @ {BUF:#x}")
    selftest(hook)
    if "--write" not in sys.argv:
        print("dry run only; pass --write to deploy")
        return

    from usb_link import LumixServiceUSB
    with LumixServiceUSB() as u:
        live = u.read_mem(TARGET, 4)
        print("validator bytes:", live.hex())
        if live == EXPECTED_PATCH:
            print("detour already present, refreshing cave/counter/buf")
        elif live != ORIG:
            raise RuntimeError(f"unexpected bytes at {TARGET:#x}: {live.hex()}")
        u.write_mem_safe(COUNTER, b"\x00" * 4, backup_path=BK_DIR + r"\dump_counter_backup.json")
        u.write_mem_safe(BUF, b"\x00" * 0x100, backup_path=BK_DIR + r"\dump_buf_backup.json")
        u.write_mem_safe(CAVE, hook, backup_path=BK_DIR + r"\dump_cave_backup.json")
        if live != EXPECTED_PATCH:
            u.write_mem_safe(TARGET, EXPECTED_PATCH, backup_path=BK_DIR + r"\dump_target_backup.json")
        assert u.read_mem(CAVE, len(hook)) == hook
        assert u.read_mem(TARGET, 4) == EXPECTED_PATCH
        print("counter =", struct.unpack("<I", u.read_mem(COUNTER, 4))[0])
    print("\nDEPLOYED. Warm-reboot to normal mode, run the lens update with the official")
    print("400BV020.plf (it will say 'already installed'), then return to service mode")
    print("and read BUF 0x87086400 (0x100 bytes) + counter 0x87086380. Do NOT pull battery.")


if __name__ == "__main__":
    main()
