"""Re-deploy the lens-header-validator detour after the battery pull wiped RAM.

Target : 0x868C5E48  lens .plf header/version validator entry (cold, Thumb-2)
         original first insn = 2de9ff4f (push.w {...}), 4 bytes
Cave   : 0x87086300  rodata (survives warm reboot, executable)
Counter: 0x87086340  rodata, incremented once per validator invocation
Resume : 0x868C5E4C  remaining original function body, behaviour 100% preserved

The detour patch equals the previous session's bytes (c0f35ab2), so this is a
faithful reconstruction of what was deployed before the battery pull.

Dry run (capstone + unicorn selftest) by default; --write deploys to camera.
"""
import struct
import sys

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP,
)

from inject_test import bw, movw_movt

TARGET = 0x868C5E48
ORIG = bytes.fromhex("2de9ff4f")          # push.w {r0-r11, lr} prologue
RESUME = TARGET + 4
CAVE = 0x87086300
COUNTER = 0x87086340
EXPECTED_PATCH = bytes.fromhex("c0f35ab2")  # last session's detour bytes
BK_DIR = r"E:\desktop\LUMIX"


def build_hook():
    code = bytearray()
    code += struct.pack("<H", 0xB40F)              # push {r0-r3}
    code += movw_movt(2, COUNTER & 0xFFFF)          # movw r2, #low
    code += movw_movt(2, COUNTER >> 16, True)       # movt r2, #high
    code += struct.pack("<H", 0x6813)               # ldr r3, [r2]
    code += struct.pack("<H", 0x3301)               # adds r3, #1
    code += struct.pack("<H", 0x6013)               # str r3, [r2]
    code += struct.pack("<H", 0xBC0F)               # pop {r0-r3}
    code += ORIG                                    # original push.w prologue
    code += bw(CAVE + len(code), RESUME)            # resume original function
    return bytes(code)


def selftest(hook, patch):
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    print("--- hook disassembly ---")
    for ins in md.disasm(hook, CAVE):
        print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
    print("--- patch at validator ---")
    for ins in md.disasm(patch, TARGET):
        print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
    assert patch == EXPECTED_PATCH, f"patch {patch.hex()} != last session {EXPECTED_PATCH.hex()}"

    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    mu.mem_map(0x87086000, 0x10000)
    mu.mem_map(0x868C5000, 0x10000)
    mu.mem_map(0x80000000, 0x10000)  # stack + return landing pad
    mu.mem_write(CAVE, hook)
    mu.mem_write(TARGET, patch)
    mu.mem_write(RESUME, struct.pack("<H", 0x4770))  # bx lr (stands in for body)
    mu.mem_write(COUNTER, struct.pack("<I", 0))
    ret = 0x80001000
    mu.mem_write(ret, struct.pack("<H", 0x4770))
    for reg, val in ((UC_ARM_REG_R0, 0x11111111), (UC_ARM_REG_R1, 0x22222222),
                     (UC_ARM_REG_R2, 0x33333333), (UC_ARM_REG_R3, 0x44444444)):
        mu.reg_write(reg, val)
    mu.reg_write(UC_ARM_REG_LR, ret | 1)
    mu.reg_write(UC_ARM_REG_SP, 0x80008000)
    mu.reg_write(UC_ARM_REG_PC, TARGET | 1)
    mu.emu_start(TARGET | 1, ret, count=64)
    got = struct.unpack("<I", mu.mem_read(COUNTER, 4))[0]
    regs = [mu.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
    print(f"emulation: counter={got}, r0-r3={[hex(r) for r in regs]}, pc={mu.reg_read(UC_ARM_REG_PC):#x}")
    assert got == 1, "counter did not increment"
    assert regs == [0x11111111, 0x22222222, 0x33333333, 0x44444444], "argument registers clobbered"
    print("SELFTEST PASS: counter incremented, registers preserved, returned to caller")


def main():
    hook = build_hook()
    patch = bw(TARGET, CAVE)
    print(f"hook {len(hook)} bytes @ {CAVE:#x}, counter @ {COUNTER:#x}, resume @ {RESUME:#x}")
    selftest(hook, patch)
    if "--write" not in sys.argv:
        print("dry run only; pass --write to deploy to the camera")
        return

    from usb_link import LumixServiceUSB
    with LumixServiceUSB() as u:
        live = u.read_mem(TARGET, 4)
        print("original validator bytes:", live.hex())
        if live == EXPECTED_PATCH:
            print("detour already in place, refreshing cave+counter only")
        elif live != ORIG:
            raise RuntimeError(f"unexpected bytes at {TARGET:#x}: {live.hex()} - aborting")
        u.write_mem_safe(COUNTER, b"\x00" * 4, backup_path=BK_DIR + r"\redeploy_counter_backup.json")
        u.write_mem_safe(CAVE, hook, backup_path=BK_DIR + r"\redeploy_cave_backup.json")
        if live != EXPECTED_PATCH:
            u.write_mem_safe(TARGET, patch, backup_path=BK_DIR + r"\redeploy_target_backup.json")
        print("cave readback :", u.read_mem(CAVE, len(hook)).hex())
        print("patch readback:", u.read_mem(TARGET, 4).hex())
        assert u.read_mem(CAVE, len(hook)) == hook
        assert u.read_mem(TARGET, 4) == EXPECTED_PATCH
        print("counter =", struct.unpack("<I", u.read_mem(COUNTER, 4))[0])
    print("\nDEPLOYED. Run the lens update from the menu, then read the counter.")
    print("If it spins: do NOT pull the battery - warm reboot only (power off/on).")


if __name__ == "__main__":
    main()
