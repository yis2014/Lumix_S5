"""Find every Thumb BL (direct call) whose target is one of the given addresses."""
import struct
import sys

BIN = r"E:\desktop\LUMIX\program_0x86280000.bin"
BASE = 0x86280000
blob = open(BIN, "rb").read()


def bl_target(addr, hw1, hw2):
    s = (hw1 >> 10) & 1
    imm10 = hw1 & 0x3FF
    j1 = (hw2 >> 13) & 1
    j2 = (hw2 >> 11) & 1
    imm11 = hw2 & 0x7FF
    i1 = (~(j1 ^ s)) & 1
    i2 = (~(j2 ^ s)) & 1
    imm32 = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if s:
        imm32 -= 1 << 25
    return (addr + 4 + imm32) & 0xFFFFFFFF


def find_calls(targets):
    hits = {t: [] for t in targets}
    n = len(blob)
    for off in range(0, n - 4, 2):
        hw1, hw2 = struct.unpack_from("<HH", blob, off)
        if (hw1 & 0xF800) != 0xF000 or (hw2 & 0xD000) != 0xD000:
            continue
        addr = BASE + off
        t = bl_target(addr, hw1, hw2)
        for cand in (t, t + 0x80000000, t - 0x80000000):
            if cand in hits:
                hits[cand].append(addr)
    return hits


if __name__ == "__main__":
    targets = [int(a, 0) for a in sys.argv[1:]] or [0x864783B4]
    for t, sites in find_calls(targets).items():
        print(f"\n=== calls to 0x{t:08x}: {len(sites)} ===")
        for s in sites[:40]:
            print(f"  from 0x{s:08x}")
