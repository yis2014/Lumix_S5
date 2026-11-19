"""Capture the payload AES key during a genuine firmware update.

Two independent hooks in rodata (survives warm power-button reboots), each with
its own counter so we can tell exactly which crypto path the updater uses:

  hook A  0x868550EC  set_key(ctx=r0, key=r1)  -> copy 32 bytes from r1
  hook B  0x86855116  key_schedule(ctx=r0)     -> copy 32 bytes from ctx+0x170

Both preserve r0-r3, replay the original first 4 bytes and branch back.
The camera flashes the UNMODIFIED official V2.9 payload; only RAM is patched.
"""
import struct
import sys

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_LR, UC_ARM_REG_SP,
)

from inject_test import bw, movw_movt
from usb_link import LumixServiceUSB

CAVE = 0x8708619A
BUF_A = 0x8F000100
BUF_B = 0x8F000140
BUF_C = 0x8F000180
BUF_D = 0x8F0001C0
BACKUP = r"E:\desktop\LUMIX\key_hook_backup.json"
IMAGE = r"E:\desktop\LUMIX\program_0x86280000.bin"
BASE = 0x86280000

TARGETS = [
    ("A_setkey", 0x868550EC, BUF_A, "r1"),
    ("B_schedule", 0x86855116, BUF_B, "ctx"),
    ("C_expand", 0x868C0612, BUF_C, "r1"),
    ("D_updparse", 0x868C6B14, BUF_D, "none"),
]


def ldr_imm(rt, rn, off):
    return struct.pack("<H", 0x6800 | ((off // 4) << 6) | (rn << 3) | rt)


def str_imm(rt, rn, off):
    return struct.pack("<H", 0x6000 | ((off // 4) << 6) | (rn << 3) | rt)


def build_hook(cave, target, buf, src_mode, image):
    c = bytearray()
    c += struct.pack("<H", 0xB40F)                    # push {r0-r3}
    c += movw_movt(2, buf & 0xFFFF)                   # r2 = capture buffer
    c += movw_movt(2, buf >> 16, True)
    if src_mode == "r1":
        c += struct.pack("<H", 0x1C0B)                # adds r3, r1, #0
    elif src_mode == "ctx":
        c += struct.pack("<H", 0x1C03)                # adds r3, r0, #0
        c += struct.pack("<H", 0x3380)                # adds r3, #0x80
        c += struct.pack("<H", 0x33F0)                # adds r3, #0xF0 (= +0x170)
    if src_mode != "none":
        for off in range(0, 32, 4):
            c += ldr_imm(0, 3, off)
            c += str_imm(0, 2, off)
    c += ldr_imm(0, 2, 0x20)
    c += struct.pack("<H", 0x3001)                    # adds r0, #1
    c += str_imm(0, 2, 0x20)
    c += struct.pack("<H", 0xBC0F)                    # pop {r0-r3}
    c += image[target - BASE: target - BASE + 4]      # original first 4 bytes
    c += bw(cave + len(c), target + 4)                # resume original function
    return bytes(c)


def layout(image):
    addr = CAVE
    out = []
    for name, target, buf, mode in TARGETS:
        h = build_hook(addr, target, buf, mode, image)
        out.append((name, addr, target, buf, mode, h))
        addr += (len(h) + 3) & ~3
    assert addr < BUF_A, "hook code overlaps capture buffer"
    return out


def selftest(hooks):
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    for name, cave, target, buf, mode, hook in hooks:
        print(f"--- {name} @ {cave:#x} ({len(hook)} bytes) ---")
        for ins in md.disasm(hook, cave):
            print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
        mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        mu.mem_map(0x87080000, 0x10000)
        mu.mem_map(0x80000000, 0x10000)
        mu.mem_map(0x8F000000, 0x1000)
        mu.mem_map(target & ~0xFFF, 0x1000)
        mu.mem_write(cave, hook)
        mu.mem_write(target + 4, struct.pack("<H", 0x4770))   # original body: bx lr
        src = 0x80004000
        key = bytes(range(1, 33))
        mu.mem_write(src, key)
        mu.mem_write(buf, b"\x00" * 0x24)
        ret = 0x80002000
        mu.mem_write(ret, struct.pack("<H", 0x4770))
        for reg, val in ((UC_ARM_REG_R0, src), (UC_ARM_REG_R1, src),
                         (UC_ARM_REG_R2, 0xDEADBEEF), (UC_ARM_REG_R3, 0x12345678)):
            mu.reg_write(reg, val)
        mu.reg_write(UC_ARM_REG_SP, 0x80008000)
        mu.reg_write(UC_ARM_REG_LR, ret | 1)
        mu.emu_start(cave | 1, ret, count=400)
        got = bytes(mu.mem_read(buf, 32))
        cnt = struct.unpack("<I", mu.mem_read(buf + 0x20, 4))[0]
        r2 = mu.reg_read(UC_ARM_REG_R2)
        r3 = mu.reg_read(UC_ARM_REG_R3)
        print(f"  emu: key_match={got == key} counter={cnt} r2={r2:#x} r3={r3:#x}")
        assert cnt == 1 and r2 == 0xDEADBEEF and r3 == 0x12345678
        if mode == "r1":
            assert got == key
    print("SELFTEST PASS")


def main():
    image = open(IMAGE, "rb").read()
    hooks = layout(image)
    selftest(hooks)
    if "--write" not in sys.argv:
        print("dry run; use --write to deploy")
        return
    with LumixServiceUSB() as u:
        for name, cave, target, buf, mode, h in hooks:
            print(f"{name}: orig={u.read_mem(target, 4).hex()} dump={image[target - BASE: target - BASE + 4].hex()}")
            u.write_mem_safe(buf, b"\x00" * 0x24, backup_path=BACKUP)
            u.write_mem_safe(cave, h, backup_path=BACKUP)
            u.write_mem_safe(target, bw(target, cave), backup_path=BACKUP)
            print(f"   cave={u.read_mem(cave, len(h)).hex()}")
            print(f"   target={u.read_mem(target, 4).hex()} counter={struct.unpack('<I', u.read_mem(buf + 0x20, 4))[0]}")
    print("deployed")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "read":
        with LumixServiceUSB() as u:
            for name, target, buf, mode in TARGETS:
                print(f"{name}: counter={struct.unpack('<I', u.read_mem(buf + 0x20, 4))[0]} key={u.read_mem(buf, 32).hex()}")
    else:
        main()
