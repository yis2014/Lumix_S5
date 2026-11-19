"""Atomic-safe code execution proof using the COLD metadata verifier.

Instead of patching hot memcpy (which crashed when the 4-byte patch was seen
half-written), I hook the firmware metadata verifier at 0x868C08C6. It only runs
while the camera checks an update file, so writing the patch is safe, and the
hook fires BEFORE the Yes/No confirmation - no flashing is ever needed.

Hook behaviour: increment a counter, then return 0 (signature valid), exactly
like the previous 4-byte bypass, so normal update checking still works.
"""
import struct
import time

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

from inject_test import bw, movw_movt
from usb_link import LumixServiceUSB

TARGET = 0x868C08C6          # metadata ECDSA verifier wrapper
CAVE = 0x862F3000
COUNTER = 0x862F3200
BACKUP = r"E:\desktop\LUMIX\inject_cold_backup.json"


def build_hook():
    c = bytearray()
    c += struct.pack("<H", 0xB40F)                 # push {r0-r3}
    c += movw_movt(2, COUNTER & 0xFFFF)
    c += movw_movt(2, COUNTER >> 16, True)
    c += struct.pack("<H", 0x6813)                 # ldr r3, [r2]
    c += struct.pack("<H", 0x3301)                 # adds r3, #1
    c += struct.pack("<H", 0x6013)                 # str r3, [r2]
    c += struct.pack("<H", 0xBC0F)                 # pop {r0-r3}
    c += struct.pack("<H", 0x2000)                 # movs r0, #0  (signature valid)
    c += struct.pack("<H", 0x4770)                 # bx lr
    return bytes(c)


def main():
    hook = build_hook()
    patch = bw(TARGET, CAVE)
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    for ins in md.disasm(hook, CAVE):
        print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
    for ins in md.disasm(patch, TARGET):
        print(f"patch {ins.address:#x}: {ins.mnemonic} {ins.op_str}")

    with LumixServiceUSB() as u:
        print("target before:", u.read_mem(TARGET, 4).hex())
        u.write_mem_safe(COUNTER, b"\x00" * 4, backup_path=BACKUP)
        u.write_mem_safe(CAVE, hook, backup_path=BACKUP)
        u.write_mem_safe(TARGET, patch, backup_path=BACKUP)
        print("cave readback :", u.read_mem(CAVE, len(hook)).hex())
        print("target after  :", u.read_mem(TARGET, 4).hex())
        print("counter now   :", struct.unpack("<I", u.read_mem(COUNTER, 4))[0])
    print("\nNext: reboot NORMAL (no button combo), run the 2.A update check up to")
    print("the Yes/No prompt, answer No, then come back to service mode and run")
    print("  python inject_cold.py read")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "read":
        with LumixServiceUSB() as u:
            print("counter =", struct.unpack("<I", u.read_mem(COUNTER, 4))[0])
            print("cave    =", u.read_mem(CAVE, 16).hex())
            print("target  =", u.read_mem(TARGET, 4).hex())
    else:
        main()
