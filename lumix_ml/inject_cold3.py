"""Code execution proof, v3: cave placed in persistent rodata instead of BSS.

Lesson from v2: the big zero gaps in the main-core image are zero-initialised
BSS and are wiped during boot, while patches in the loaded image itself
(like 0x868C08C6) survive reboots. So the hook now lives inside a long, obscure
C++ type-info string in rodata, and the counter sits right next to it.
"""
import struct
import sys

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

from inject_test import bw, movw_movt
from usb_link import LumixServiceUSB

TARGET = 0x868C08C6
CAVE = 0x8708619A            # C++ locale/facet error strings in rodata (within b.w range)
COUNTER = CAVE + 0x40
BACKUP = r"E:\desktop\LUMIX\inject_cold3_backup.json"


def build_hook():
    c = bytearray()
    c += struct.pack("<H", 0xB40F)                 # push {r0-r3}
    c += movw_movt(2, COUNTER & 0xFFFF)
    c += movw_movt(2, COUNTER >> 16, True)
    c += struct.pack("<H", 0x6813)                 # ldr r3, [r2]
    c += struct.pack("<H", 0x3301)                 # adds r3, #1
    c += struct.pack("<H", 0x6013)                 # str r3, [r2]
    c += struct.pack("<H", 0xBC0F)                 # pop {r0-r3}
    c += struct.pack("<H", 0x2000)                 # movs r0, #0
    c += struct.pack("<H", 0x4770)                 # bx lr
    return bytes(c)


def deploy():
    hook = build_hook()
    patch = bw(TARGET, CAVE)
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    for ins in md.disasm(hook, CAVE):
        print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
    with LumixServiceUSB() as u:
        u.write_mem_safe(COUNTER, b"\x00" * 4, backup_path=BACKUP)
        u.write_mem_safe(CAVE, hook, backup_path=BACKUP)
        u.write_mem_safe(TARGET, patch, backup_path=BACKUP)
        print("cave    :", u.read_mem(CAVE, len(hook)).hex())
        print("target  :", u.read_mem(TARGET, 4).hex())
        print("counter :", struct.unpack("<I", u.read_mem(COUNTER, 4))[0])


def readback():
    with LumixServiceUSB() as u:
        print("counter =", struct.unpack("<I", u.read_mem(COUNTER, 4))[0])
        print("cave    =", u.read_mem(CAVE, 24).hex())
        print("target  =", u.read_mem(TARGET, 4).hex())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "read":
        readback()
    else:
        deploy()
