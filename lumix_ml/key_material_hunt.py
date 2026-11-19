"""Hunt key material used by the S5 crypto/update module.

Scans a code region for Thumb `ldr rX, [pc, #imm]` literal loads whose literal is a
pointer into the image's rodata, then scores the pointed-to bytes by entropy.
High-entropy 16/24/32-byte targets are AES key candidates.
"""
import math
import struct
from collections import Counter

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

BIN = r"E:\desktop\LUMIX\program_0x86280000.bin"
BASE = 0x86280000
DELTA = 0x80000000
REGION_START = 0x868B0000
REGION_END = 0x868C8000

blob = open(BIN, "rb").read()
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
md.detail = True


def ent(b):
    if not b:
        return 0.0
    c = Counter(b)
    return -sum((v / len(b)) * math.log2(v / len(b)) for v in c.values())


def main():
    code = blob[REGION_START - BASE:REGION_END - BASE]
    seen = {}
    for ins in md.disasm(code, REGION_START):
        if ins.mnemonic != "ldr" or "[pc," not in ins.op_str:
            continue
        try:
            imm = int(ins.op_str.split("#")[1].rstrip("]"), 0)
        except (ValueError, IndexError):
            continue
        lit = ((ins.address + 4) & ~3) + imm
        if not (BASE <= lit < BASE + len(blob) - 4):
            continue
        ptr = struct.unpack_from("<I", blob, lit - BASE)[0]
        if not (0x06000000 <= ptr < 0x08000000):
            continue
        target = ptr + DELTA
        if not (BASE <= target < BASE + len(blob) - 64):
            continue
        data = blob[target - BASE:target - BASE + 32]
        e = ent(data)
        printable = sum(1 for x in data if 32 <= x < 127)
        if e < 4.3 or printable > 24:
            continue
        key = (target, ins.address)
        if target in seen:
            continue
        seen[target] = ins.address
        print(f"key-candidate phys 0x{target:08x} (virt 0x{ptr:08x}) entropy={e:.2f}")
        print(f"   used by ldr @ 0x{ins.address:08x}, literal @ 0x{lit:08x}")
        print(f"   16B: {data[:16].hex()}")
        print(f"   32B: {data.hex()}")
    print(f"\n{len(seen)} candidates in region 0x{REGION_START:08x}..0x{REGION_END:08x}")


if __name__ == "__main__":
    main()
