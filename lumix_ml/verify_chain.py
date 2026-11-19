"""Trace the call chain from the firmware updater to the ECDSA verification code."""
import struct
from collections import deque

BIN = r"E:\desktop\LUMIX\program_0x86280000.bin"
BASE = 0x86280000
blob = open(BIN, "rb").read()
N = len(blob)

ECC_ZONES = [(0x86430000, 0x86434000), (0x868CD000, 0x868D0000)]
UPDATER = (0x86867000, 0x86867800)


def bl_targets(start, end):
    out = []
    for a in range(start, end - 4, 2):
        o = a - BASE
        hw1, hw2 = struct.unpack_from("<HH", blob, o)
        if (hw1 & 0xF800) != 0xF000:
            continue
        if (hw2 & 0xD000) != 0xD000:
            continue
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
        out.append((a, (a + 4 + imm32) & 0xFFFFFFFF))
    return out


def in_ecc(addr):
    return any(lo <= addr < hi for lo, hi in ECC_ZONES)


def main():
    # BFS over call graph, starting from every call in the updater body
    queue = deque()
    parent = {}
    for site, target in bl_targets(*UPDATER):
        if BASE <= target < BASE + N and target not in parent:
            parent[target] = site
            queue.append(target)
    found = []
    depth = {t: 0 for t in parent}
    while queue:
        fn = queue.popleft()
        d = depth[fn]
        if d > 3:
            continue
        # scan a function body window (heuristic 0x400 bytes)
        for site, target in bl_targets(fn, min(fn + 0x400, BASE + N)):
            if in_ecc(target):
                found.append((fn, site, target, d))
            if BASE <= target < BASE + N and target not in parent:
                parent[target] = site
                depth[target] = d + 1
                queue.append(target)
    print(f"visited {len(parent)} functions; {len(found)} edges into ECC zones")
    for fn, site, target, d in found[:25]:
        print(f"  depth={d} caller_fn=0x{fn:08x} bl@0x{site:08x} -> 0x{target:08x}")


if __name__ == "__main__":
    main()
