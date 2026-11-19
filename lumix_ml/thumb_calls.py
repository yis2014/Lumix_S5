"""Offline Thumb-2 call-graph helpers for the S5 program image.

Scans the whole 30 MiB image for BL (branch-with-link) instructions that target a
given function, then disassembles context around each hit.
"""
import struct
import sys

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

BIN = r"E:\desktop\LUMIX\program_0x86280000.bin"
BASE = 0x86280000

md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)


def bl_target(hw1, hw2, addr):
    """Decode a Thumb-2 BL immediate; return target or None."""
    if (hw1 & 0xF800) != 0xF000:
        return None
    if (hw2 & 0xD000) != 0xD000:  # 11 J1 1 J2
        return None
    s = (hw1 >> 10) & 1
    imm10 = hw1 & 0x03FF
    j1 = (hw2 >> 13) & 1
    j2 = (hw2 >> 11) & 1
    imm11 = hw2 & 0x07FF
    i1 = (~(j1 ^ s)) & 1
    i2 = (~(j2 ^ s)) & 1
    imm32 = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if s:
        imm32 -= 1 << 25
    return (addr + 4 + imm32) & 0xFFFFFFFF


def find_callers(blob, target):
    hits = []
    for off in range(0, len(blob) - 4, 2):
        hw1, hw2 = struct.unpack_from("<HH", blob, off)
        t = bl_target(hw1, hw2, BASE + off)
        if t == (target & ~1):
            hits.append(BASE + off)
    return hits


def disasm(blob, addr, size=0x80, mark=None):
    code = blob[addr - BASE:addr - BASE + size]
    out = []
    for ins in md.disasm(code, addr & ~1):
        prefix = ">>" if mark is not None and ins.address == (mark & ~1) else "  "
        out.append(f"{prefix}0x{ins.address:08x}: {ins.mnemonic:10s} {ins.op_str}")
    return "\n".join(out)


def main():
    with open(BIN, "rb") as f:
        blob = f.read()

    targets = [int(a, 16) for a in sys.argv[1:]] or [0x8775C210]
    for t in targets:
        print(f"\n########## callers of 0x{t:08x} ##########")
        hits = find_callers(blob, t)
        print(f"{len(hits)} BL site(s): {[hex(h) for h in hits]}")
        for h in hits[:6]:
            print(f"\n--- context around 0x{h:08x} ---")
            print(disasm(blob, h - 0x40, 0x60, mark=h))

    # Always dump the object-provider helper
    helper = 0x8774F182
    print(f"\n########## object provider 0x{helper:08x} ##########")
    print(disasm(blob, helper, 0x120))


if __name__ == "__main__":
    main()
