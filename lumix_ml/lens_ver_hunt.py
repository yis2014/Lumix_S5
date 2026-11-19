"""Locate the lens .plf header parser and its version-check logic.

1. Find LENS-UPDATE-FILE-SOF / CABRIOLET / LENS_FW_UPDATE_MODE strings.
2. Find code references (movw/movt pairs and pc-relative LDR) to those strings.
3. Disassemble around each reference so the version-field comparison can be read.
"""
import struct
import sys

import numpy as np

from thumb_calls import disasm, BIN, BASE

blob = open(BIN, "rb").read()


def find_string(needle):
    out = []
    start = 0
    while True:
        i = blob.find(needle, start)
        if i < 0:
            break
        out.append(BASE + i)
        start = i + 1
    return out


def movw_sites(value):
    """All Thumb movw rd, #imm16 sites whose imm16 == value & 0xFFFF."""
    imm16 = value & 0xFFFF
    imm4 = (imm16 >> 12) & 0xF
    i = (imm16 >> 11) & 1
    imm3 = (imm16 >> 8) & 0x7
    imm8 = imm16 & 0xFF
    hw1 = 0xF240 | (i << 10) | imm4
    hits = []
    for rd in range(15):
        hw2 = (imm3 << 12) | (rd << 8) | imm8
        pat = struct.pack("<HH", hw1, hw2)
        start = 0
        while True:
            j = blob.find(pat, start)
            if j < 0:
                break
            hits.append((BASE + j, rd))
            start = j + 2
    return hits


def ldr_sites(target, window=0x40):
    """Thumb-16 pc-relative LDR sites whose literal address is near target."""
    n2 = len(blob) // 2 * 2
    h = np.frombuffer(blob[:n2], dtype="<u2")
    sel = np.nonzero((h >> 11) == 0b01001)[0]
    hits = []
    for i in sel:
        a = BASE + int(i) * 2
        pc = (a + 4) & ~2
        t = pc + int(h[i] & 0xFF) * 4
        if abs(t - target) <= window:
            hits.append(a)
    return hits


def main():
    needles = [b"LENS-UPDATE-FILE-SOF", b"LENS-UPDATE-FILE-EOH",
               b"CABRIOLET", b"LENS_FW_UPDATE_MODE", b"fw_ver=%s"]
    for n in needles:
        addrs = find_string(n)
        print(f"\n===== {n.decode()} -> {[hex(a) for a in addrs]} =====")
        for a in addrs:
            sites = movw_sites(a)
            print(f"  movw sites for 0x{a:08x}: {[hex(s) for s, _ in sites]}")
            for s, _ in sites[:4]:
                print(disasm(blob, s - 0x8, 0x70, mark=s))
                print("  ----")
            ls = ldr_sites(a)
            if ls:
                print(f"  ldr sites near 0x{a:08x}: {[hex(s) for s in ls]}")


if __name__ == "__main__":
    main()
