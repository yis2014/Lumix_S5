"""Capture FW-update globals at 0x87F4D32E, then abort before its body runs.

The only caller handles a non-zero return through its existing error path.  The
hook therefore copies the two static objects used by the worker and returns 1
without executing the worker prologue or any of its NAND read/write calls.

RAM-only deployment.  Capstone + Unicorn self-test runs before --write.
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

TARGET = 0x87F4D32E
ORIG = bytes.fromhex("2de9f04f")
PATCH = bw(TARGET, 0x87086300)

NAND_TARGET = 0x87F4D152
NAND_ORIG = bytes.fromhex("2de9f041")
NAND_PATCH = bytes.fromhex("39f5d590")
LENS_TARGET = 0x868C5E48
LENS_ORIG = bytes.fromhex("2de9ff4f")
LENS_PATCH = bytes.fromhex("c0f35ab2")

G_LITERAL = 0x87F4D4C4
G_EXPECTED = 0x0C11DA38
S_LITERAL = 0x87F4D554
S_EXPECTED = 0x0C2110A4

CAVE = 0x87086300
BUF = 0x87086400
COUNTER = 0x870864F0
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

    movw r1, #{G_LITERAL & 0xFFFF}
    movt r1, #{G_LITERAL >> 16}
    ldr r1, [r1]
    str r1, [r4, #0x40]
    lsrs r2, r1, #24
    cmp r2, #0x06
    blo {{skip_g}}
    cmp r2, #0x0e
    bhs {{skip_g}}
    add r0, r4, #0x60
    movs r2, #0x10
copy_g:
    ldr r3, [r1]
    adds r1, #4
    str r3, [r0]
    adds r0, #4
    subs r2, #1
    bne {{copy_g}}
skip_g:

    movw r1, #{S_LITERAL & 0xFFFF}
    movt r1, #{S_LITERAL >> 16}
    ldr r1, [r1]
    str r1, [r4, #0x44]
    lsrs r2, r1, #24
    cmp r2, #0x06
    blo {{skip_s}}
    cmp r2, #0x0e
    bhs {{skip_s}}
    add r0, r4, #0xa0
    movs r2, #0x10
copy_s:
    ldr r3, [r1]
    adds r1, #4
    str r3, [r0]
    adds r0, #4
    subs r2, #1
    bne {{copy_s}}
skip_s:
    pop {{r0-r4}}
    movs r0, #1
    bx lr
"""


def build_hook():
    return assemble(HOOK_ASM.splitlines(), CAVE)


def selftest(hook):
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    print(f"--- FW-update entry capture/abort hook {len(hook)} bytes ---")
    for ins in md.disasm(hook, CAVE):
        print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")

    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    mu.mem_map(0x87080000, 0x20000)
    mu.mem_map(0x87F4D000, 0x10000)
    mu.mem_map(0x0C110000, 0x10000)
    mu.mem_map(0x0C210000, 0x10000)
    mu.mem_map(0x80000000, 0x10000)
    mu.mem_write(CAVE, hook)
    mu.mem_write(TARGET, PATCH)
    mu.mem_write(G_LITERAL, struct.pack("<I", G_EXPECTED))
    mu.mem_write(S_LITERAL, struct.pack("<I", S_EXPECTED))
    mu.mem_write(COUNTER, b"\x00" * 4)
    mu.mem_write(BUF, b"\x00" * 0x100)
    g_bytes = bytes(range(0x40))
    s_bytes = bytes(range(0x40, 0x80))
    mu.mem_write(G_EXPECTED, g_bytes)
    mu.mem_write(S_EXPECTED, s_bytes)
    ret = 0x80001000
    mu.mem_write(ret, struct.pack("<H", 0x4770))
    initial = [0, 0x22222222, 0x33333333, 0x44444444, 0x55555555]
    for reg, val in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                         UC_ARM_REG_R3, UC_ARM_REG_R4), initial):
        mu.reg_write(reg, val)
    mu.reg_write(UC_ARM_REG_LR, ret | 1)
    mu.reg_write(UC_ARM_REG_SP, 0x80008000)
    mu.reg_write(UC_ARM_REG_PC, TARGET | 1)
    mu.emu_start(TARGET | 1, ret, count=500)

    dump = bytes(mu.mem_read(BUF, 0x100))
    saved = struct.unpack_from("<6I", dump, 0)
    assert struct.unpack("<I", mu.mem_read(COUNTER, 4))[0] == 1
    assert saved[:4] == tuple(initial[:4]) and saved[5] == (ret | 1)
    assert struct.unpack_from("<II", dump, 0x40) == (G_EXPECTED, S_EXPECTED)
    assert dump[0x60:0xA0] == g_bytes and dump[0xA0:0xE0] == s_bytes
    after = [mu.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1,
             UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4)]
    assert after == [1] + initial[1:], after
    print("SELFTEST PASS: G/S captured, r1-r4 preserved, r0=1 returned to caller;")


def main():
    hook = build_hook()
    print(f"target={TARGET:#x} patch={PATCH.hex()} cave={CAVE:#x}")
    selftest(hook)
    if "--write" not in sys.argv:
        print("dry run only; pass --write to deploy")
        return

    from usb_link import LumixServiceUSB
    with LumixServiceUSB() as u:
        nand_live = u.read_mem(NAND_TARGET, 4)
        lens_live = u.read_mem(LENS_TARGET, 4)
        target_live = u.read_mem(TARGET, 4)
        print("old NAND entry:", nand_live.hex())
        print("lens entry     :", lens_live.hex())
        print("worker entry   :", target_live.hex())
        if nand_live not in (NAND_ORIG, NAND_PATCH):
            raise RuntimeError(f"unexpected old NAND entry {nand_live.hex()}")
        if lens_live not in (LENS_ORIG, LENS_PATCH):
            raise RuntimeError(f"unexpected lens entry {lens_live.hex()}")
        if target_live not in (ORIG, PATCH):
            raise RuntimeError(f"unexpected worker entry {target_live.hex()}")

        # Release the shared cave before replacing its payload.
        if nand_live == NAND_PATCH:
            u.write_mem_safe(NAND_TARGET, NAND_ORIG,
                             backup_path=BK_DIR + r"\fwentry_nand_restore_backup.json")
        if lens_live == LENS_PATCH:
            u.write_mem_safe(LENS_TARGET, LENS_ORIG,
                             backup_path=BK_DIR + r"\fwentry_lens_restore_backup.json")
        assert u.read_mem(NAND_TARGET, 4) == NAND_ORIG
        assert u.read_mem(LENS_TARGET, 4) == LENS_ORIG

        u.write_mem_safe(COUNTER, b"\x00" * 4, backup_path=BK_DIR + r"\fwentry_counter_backup.json")
        u.write_mem_safe(BUF, b"\x00" * 0x100, backup_path=BK_DIR + r"\fwentry_buf_backup.json")
        u.write_mem_safe(CAVE, hook, backup_path=BK_DIR + r"\fwentry_cave_backup.json")
        if target_live != PATCH:
            u.write_mem_safe(TARGET, PATCH, backup_path=BK_DIR + r"\fwentry_target_backup.json")
        assert u.read_mem(CAVE, len(hook)) == hook
        assert u.read_mem(TARGET, 4) == PATCH
        print("counter =", struct.unpack("<I", u.read_mem(COUNTER, 4))[0])

    print("\nDEPLOYED FW-update entry capture/abort. The worker body will not run.")
    print("After the user triggers the official body-update path and returns to")
    print("service mode, run read_fwupdate_entry_dump.py. Do NOT pull battery.")


if __name__ == "__main__":
    main()
