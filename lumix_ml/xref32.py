"""Universal code-reference finder for the S5 main-core image.

Covers three Thumb-2 reference forms that earlier tools missed:
  - movw/movt immediate pairs (via movw low half)
  - 16-bit pc-relative LDR
  - 32-bit pc-relative LDR.W (the blind spot of earlier scans)
Usage: python xref32.py <hexaddr> [more hexaddr...]
"""
import struct
import sys

import numpy as np

from thumb_calls import disasm, BIN, BASE

blob = open(BIN, "rb").read()


def movw_sites(value):
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
            hits.append(BASE + j)
            start = j + 2
    return hits


def ldr16_sites(target, window=0):
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


def ldr32_sites(target, window=0):
    """LDR.W Rt, [PC, #+/-imm12]: hw1 1111 1000 0U01 1111, hw2 Rt|imm12."""
    n2 = len(blob) // 2 * 2
    h = np.frombuffer(blob[:n2], dtype="<u2")
    h1 = h[:-1]
    h2 = h[1:]
    mask = (h1 & 0xFF7F) == 0xF85F
    idx = np.nonzero(mask)[0]
    hits = []
    for i in idx:
        a = BASE + int(i) * 2
        up = (int(h1[i]) >> 7) & 1
        imm = int(h2[i]) & 0xFFF
        pc = (a + 4) & ~3
        t = pc + imm if up else pc - imm
        if abs(t - target) <= window:
            hits.append(a)
    return hits


def movt_sites(value):
    """movt rd, #imm16 sites (for addresses whose low half is zero)."""
    imm16 = (value >> 16) & 0xFFFF
    imm4 = (imm16 >> 12) & 0xF
    i = (imm16 >> 11) & 1
    imm3 = (imm16 >> 8) & 0x7
    imm8 = imm16 & 0xFF
    hw1 = 0xF2C0 | (i << 10) | imm4
    hits = []
    for rd in range(15):
        hw2 = (imm3 << 12) | (rd << 8) | imm8
        pat = struct.pack("<HH", hw1, hw2)
        start = 0
        while True:
            j = blob.find(pat, start)
            if j < 0:
                break
            hits.append(BASE + j)
            start = j + 2
    return hits


def adr_sites(target, window=0):
    """16-bit ADR: 1010 0 Rd imm8 -> Align(PC,4) + imm8*4 (verified against dump)."""
    n2 = len(blob) // 2 * 2
    h = np.frombuffer(blob[:n2], dtype="<u2")
    sel = np.nonzero((h >> 11) == 0b10100)[0]
    hits = []
    for i in sel:
        a = BASE + int(i) * 2
        pc = (a + 4) & ~3
        t = pc + int(h[i] & 0xFF) * 4
        if abs(t - target) <= window:
            hits.append(a)
    return hits


def main():
    for arg in sys.argv[1:]:
        tgt = int(arg, 0)
        print(f"\n===== refs to {tgt:#x} =====")
        ms = movw_sites(tgt)
        mt = movt_sites(tgt) if (tgt & 0xFFFF) == 0 else []
        l16 = ldr16_sites(tgt)
        l32 = ldr32_sites(tgt)
        ad = adr_sites(tgt)
        print(f"movw: {[hex(x) for x in ms]}")
        if mt:
            print(f"movt: {[hex(x) for x in mt]}")
        print(f"ldr16:{[hex(x) for x in l16]}")
        print(f"ldr32:{[hex(x) for x in l32]}")
        print(f"adr:  {[hex(x) for x in ad]}")
        for s in (ms + mt + l16 + l32 + ad)[:4]:
            print(disasm(blob, s - 0x10, 0x50, mark=s))
            print("----")


if __name__ == "__main__":
    main()
