"""Main-core RAM code-injection proof of concept for the Panasonic DC-S5.

A 24-byte Thumb hook is placed in an unused, zero-filled gap of the main core
image. The memcpy trampoline at 0x866C22B4 is redirected to it. The hook only
increments a counter, restores every register it touched and resumes the
original memcpy, so the camera keeps working normally.

Everything is RAM only and uses the existing 0x9c halfword write channel.
The generated code is verified twice before any camera write:
  1. disassembled with capstone to prove the encodings are what I intended;
  2. executed in unicorn to prove registers are preserved and control returns.
"""
import struct
import sys

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP

MEMCPY = 0x866C22B4
MEMCPY_BODY = 0x866C295E
CAVE = 0x862F3000
COUNTER = 0x862F3200
BACKUP = r"E:\desktop\LUMIX\inject_backup.json"


def movw_movt(rd, value, movt=False):
    imm4 = (value >> 12) & 0xF
    i = (value >> 11) & 1
    imm3 = (value >> 8) & 7
    imm8 = value & 0xFF
    hw1 = 0xF000 | (i << 10) | ((0x2C0 if movt else 0x240)) | imm4
    hw2 = (imm3 << 12) | (rd << 8) | imm8
    return struct.pack("<HH", hw1, hw2)


def bw(addr, target):
    off = target - (addr + 4)
    assert off % 2 == 0 and abs(off) < (1 << 24), hex(off)
    s = (off >> 24) & 1
    i1 = (off >> 23) & 1
    i2 = (off >> 22) & 1
    imm10 = (off >> 12) & 0x3FF
    imm11 = (off >> 1) & 0x7FF
    j1 = (not (i1 ^ s)) & 1
    j2 = (not (i2 ^ s)) & 1
    return struct.pack("<HH", 0xF000 | (s << 10) | imm10,
                       0x9000 | (j1 << 13) | (j2 << 11) | imm11)


def build_hook():
    code = bytearray()
    code += struct.pack("<H", 0xB40F)              # push {r0-r3}
    code += movw_movt(2, COUNTER & 0xFFFF)          # movw r2, #low
    code += movw_movt(2, COUNTER >> 16, True)       # movt r2, #high
    code += struct.pack("<H", 0x6813)               # ldr r3, [r2]
    code += struct.pack("<H", 0x3301)               # adds r3, #1
    code += struct.pack("<H", 0x6013)               # str r3, [r2]
    code += struct.pack("<H", 0xBC0F)               # pop {r0-r3}
    code += struct.pack("<H", 0x4603)               # movs r3, r0 (original prologue)
    code += bw(CAVE + len(code), MEMCPY_BODY)       # resume original memcpy
    return bytes(code)


def build_patch():
    return bw(MEMCPY, CAVE)


def selftest(hook, patch):
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    print("--- hook disassembly ---")
    for ins in md.disasm(hook, CAVE):
        print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
    print("--- patch at memcpy ---")
    for ins in md.disasm(patch, MEMCPY):
        print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")

    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    mu.mem_map(0x862F0000, 0x10000)
    mu.mem_map(0x866C2000, 0x10000)
    mu.mem_map(0x80000000, 0x10000)  # stack
    mu.mem_write(CAVE, hook)
    mu.mem_write(MEMCPY, patch)
    mu.mem_write(MEMCPY_BODY, struct.pack("<H", 0x4770))  # bx lr
    mu.mem_write(COUNTER, struct.pack("<I", 0))
    ret = 0x80001000
    mu.mem_write(ret, struct.pack("<H", 0x4770))
    for reg, val in ((UC_ARM_REG_R0, 0x11111111), (UC_ARM_REG_R1, 0x22222222),
                     (UC_ARM_REG_R2, 0x33333333), (UC_ARM_REG_R3, 0x44444444)):
        mu.reg_write(reg, val)
    mu.reg_write(UC_ARM_REG_LR, ret | 1)
    mu.reg_write(UC_ARM_REG_SP, 0x80008000)
    mu.reg_write(UC_ARM_REG_PC, MEMCPY | 1)
    mu.emu_start(MEMCPY | 1, ret, count=64)
    got = struct.unpack("<I", mu.mem_read(COUNTER, 4))[0]
    regs = [mu.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
    print(f"emulation: counter={got}, r0-r3={[hex(r) for r in regs]}, pc={mu.reg_read(UC_ARM_REG_PC):#x}")
    assert got == 1, "counter did not increment"
    assert regs[:3] == [0x11111111, 0x22222222, 0x33333333], "argument registers clobbered"
    assert regs[3] == 0x11111111, "original 'movs r3, r0' was not reproduced"
    print("SELFTEST PASS: counter incremented, registers preserved, returned to caller")


def main():
    hook = build_hook()
    patch = build_patch()
    print(f"hook {len(hook)} bytes @ {CAVE:#x}, counter @ {COUNTER:#x}")
    selftest(hook, patch)
    if "--write" not in sys.argv:
        print("dry run only; pass --write to deploy to the camera")
        return

    from usb_link import LumixServiceUSB
    with LumixServiceUSB() as u:
        print("original memcpy bytes:", u.read_mem(MEMCPY, 4).hex())
        u.write_mem_safe(COUNTER, b"\x00" * 4, backup_path=BACKUP)
        u.write_mem_safe(CAVE, hook, backup_path=BACKUP)
        u.write_mem_safe(MEMCPY, patch, backup_path=BACKUP)
        print("cave readback :", u.read_mem(CAVE, len(hook)).hex())
        print("patch readback:", u.read_mem(MEMCPY, 4).hex())
        import time
        for _ in range(5):
            print("counter =", struct.unpack("<I", u.read_mem(COUNTER, 4))[0])
            time.sleep(0.5)
    print("If the counter grows, main-core code execution is proven.")
    print(f"restore with usb_link.rollback({BACKUP!r}) or simply reboot.")


if __name__ == "__main__":
    main()
