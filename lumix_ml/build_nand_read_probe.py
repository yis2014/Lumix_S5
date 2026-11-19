"""Read-only capture payload for the NAND stream wrapper at 0x87F4D152.

The wrapper takes one argument: r0 points to a stream descriptor.  The hook
preserves all argument/callee-saved registers it touches, records the caller,
and copies the descriptor's first 0x20 bytes into the proven rodata BUF.

The previous lens detour shares CAVE/BUF/COUNTER.  Deployment therefore restores
the lens entry first, so the two detours can never execute the wrong payload.

Dry run (Capstone + Unicorn) by default; --write deploys to camera RAM only.
No NAND write or direct driver call is performed by this payload.
"""
import struct
import sys

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_R4, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP,
)

from build_dump_payload import assemble
from inject_test import bw

TARGET = 0x87F4D152
ORIG = bytes.fromhex("2de9f041")  # push.w {r4,r5,r6,r7,r8,lr}
RESUME = TARGET + 4
PATCH = bw(TARGET, 0x87086300)

LENS_TARGET = 0x868C5E48
LENS_ORIG = bytes.fromhex("2de9ff4f")
LENS_PATCH = bytes.fromhex("c0f35ab2")

CAVE = 0x87086300
BUF = 0x87086400
COUNTER = 0x87086450
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
    blo {{skip_obj}}
    cmp r2, #0x0b
    bhs {{skip_obj}}
    ldr r2, [r0, #0]
    str r2, [r4, #0x20]
    ldr r2, [r0, #4]
    str r2, [r4, #0x24]
    ldr r2, [r0, #8]
    str r2, [r4, #0x28]
    ldr r2, [r0, #12]
    str r2, [r4, #0x2c]
    ldr r2, [r0, #16]
    str r2, [r4, #0x30]
    ldr r2, [r0, #20]
    str r2, [r4, #0x34]
    ldr r2, [r0, #24]
    str r2, [r4, #0x38]
    ldr r2, [r0, #28]
    str r2, [r4, #0x3c]
skip_obj:
    pop {{r0-r4}}
"""


def build_hook():
    body = assemble(HOOK_ASM.splitlines(), CAVE)
    code = body + ORIG
    code += bw(CAVE + len(code), RESUME)
    return code


def selftest(hook):
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    print(f"--- NAND capture hook {len(hook)} bytes ---")
    for ins in md.disasm(hook, CAVE):
        print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
    print("--- target patch ---")
    for ins in md.disasm(PATCH, TARGET):
        print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")

    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    mu.mem_map(0x87080000, 0x20000)   # cave + buf + counter
    mu.mem_map(0x09000000, 0x10000)   # stream descriptor
    mu.mem_map(0x87F4D000, 0x10000)   # target + resume
    mu.mem_map(0x80000000, 0x10000)   # stack + return landing pad
    mu.mem_write(CAVE, hook)
    mu.mem_write(TARGET, PATCH)
    mu.mem_write(RESUME, struct.pack("<H", 0x4770))  # bx lr, stands in for body
    mu.mem_write(COUNTER, b"\x00" * 4)
    mu.mem_write(BUF, b"\x00" * 0x100)

    obj = 0x09000000
    obj_bytes = bytes(range(0x20))
    mu.mem_write(obj, obj_bytes)
    ret = 0x80001000
    mu.mem_write(ret, struct.pack("<H", 0x4770))

    def invoke(r0, r4=0x55555555):
        mu.reg_write(UC_ARM_REG_R0, r0)
        mu.reg_write(UC_ARM_REG_R1, 0x22222222)
        mu.reg_write(UC_ARM_REG_R2, 0x33333333)
        mu.reg_write(UC_ARM_REG_R3, 0x44444444)
        mu.reg_write(UC_ARM_REG_R4, r4)
        mu.reg_write(UC_ARM_REG_LR, ret | 1)
        mu.reg_write(UC_ARM_REG_SP, 0x80008000)
        mu.reg_write(UC_ARM_REG_PC, TARGET | 1)
        mu.emu_start(TARGET | 1, ret, count=200)

    invoke(obj)
    dump = bytes(mu.mem_read(BUF, 0x100))
    regs = struct.unpack_from("<6I", dump, 0)
    print("saved regs:", [hex(x) for x in regs])
    print("descriptor:", dump[0x20:0x40].hex())
    assert struct.unpack("<I", mu.mem_read(COUNTER, 4))[0] == 1
    assert regs[0] == obj and regs[1:4] == (0x22222222, 0x33333333, 0x44444444)
    assert regs[5] == (ret | 1)
    assert dump[0x20:0x40] == obj_bytes, "stream descriptor copy mismatch"
    after = [mu.reg_read(r) for r in (
        UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4
    )]
    assert after == [obj, 0x22222222, 0x33333333, 0x44444444, 0x55555555]

    # An invalid/non-DRAM r0 must be skipped without a read fault.
    invoke(0)
    assert struct.unpack("<I", mu.mem_read(COUNTER, 4))[0] == 2
    assert bytes(mu.mem_read(BUF + 0x20, 0x20)) == obj_bytes
    print("SELFTEST PASS: caller+descriptor captured, invalid pointer skipped,")
    print("               r0-r4 restored, original prologue and return preserved")


def main():
    hook = build_hook()
    print(f"target={TARGET:#x} patch={PATCH.hex()} resume={RESUME:#x}")
    print(f"cave={CAVE:#x} buf={BUF:#x} counter={COUNTER:#x}")
    selftest(hook)
    if "--write" not in sys.argv:
        print("dry run only; pass --write to deploy")
        return

    from usb_link import LumixServiceUSB
    with LumixServiceUSB() as u:
        lens_live = u.read_mem(LENS_TARGET, 4)
        target_live = u.read_mem(TARGET, 4)
        print("lens entry :", lens_live.hex())
        print("NAND entry :", target_live.hex())
        if lens_live not in (LENS_ORIG, LENS_PATCH):
            raise RuntimeError(f"unexpected lens entry {lens_live.hex()} - aborting")
        if target_live not in (ORIG, PATCH):
            raise RuntimeError(f"unexpected NAND entry {target_live.hex()} - aborting")

        # The old lens detour and this payload share CAVE.  Restore first.
        if lens_live == LENS_PATCH:
            u.write_mem_safe(
                LENS_TARGET, LENS_ORIG,
                backup_path=BK_DIR + r"\nand_lens_restore_backup.json",
            )
            assert u.read_mem(LENS_TARGET, 4) == LENS_ORIG
            print("lens detour restored before replacing the shared cave")

        u.write_mem_safe(COUNTER, b"\x00" * 4, backup_path=BK_DIR + r"\nand_counter_backup.json")
        u.write_mem_safe(BUF, b"\x00" * 0x100, backup_path=BK_DIR + r"\nand_buf_backup.json")
        u.write_mem_safe(CAVE, hook, backup_path=BK_DIR + r"\nand_cave_backup.json")
        if target_live != PATCH:
            u.write_mem_safe(TARGET, PATCH, backup_path=BK_DIR + r"\nand_target_backup.json")
        assert u.read_mem(CAVE, len(hook)) == hook
        assert u.read_mem(TARGET, 4) == PATCH
        assert u.read_mem(LENS_TARGET, 4) == LENS_ORIG
        print("counter =", struct.unpack("<I", u.read_mem(COUNTER, 4))[0])

    print("\nDEPLOYED read-only NAND capture. Warm-reboot to normal mode and run the")
    print("official lens update once (400BV020.plf; 'already installed' is enough).")
    print("Return to service mode and run read_nand_dump.py. Do NOT pull battery.")


if __name__ == "__main__":
    main()
