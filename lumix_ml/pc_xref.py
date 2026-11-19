import sys

import numpy as np

path = sys.argv[1]
base = int(sys.argv[2], 16)
targets = [int(x, 16) for x in sys.argv[3:]]

d = np.frombuffer(open(path, "rb").read(), dtype=np.uint8)
n = len(d) // 4 * 4
w = np.frombuffer(d[:n].tobytes(), dtype="<u4")
addrs = base + np.arange(len(w), dtype=np.uint64) * 4

# ARM: LDR Rd, [PC, #+/-imm]   cond=1110 (AL) or others, Rn=1111
opcode = (w >> 20) & 0xFF
rn = (w >> 16) & 0xF
is_ldr = ((opcode & 0xE7) == 0x41) & (rn == 0xF)   # I=0,L=1,Rn=PC
up = (opcode & 0x08) != 0
imm = w & 0xFFF
idx = np.nonzero(is_ldr)[0]
print("ARM pc-relative LDR count:", len(idx))
hits = 0
for i in idx:
    a = int(addrs[i])
    pc = a + 8
    t = pc + int(imm[i]) if up[i] else pc - int(imm[i])
    for tg in targets:
        if abs(t - tg) <= 0x40:
            print(f"ARM  {a:#x}: ldr r{(w[i] >> 12) & 0xF}, [pc, #{imm[i]:#x}] -> {t:#x}  (sbox {tg:#x})")
            hits += 1
print("ARM hits", hits)

# Thumb-16: 01001 Rt imm8  -> target = ((pc+4)&~2) + imm8*4
n2 = len(d) // 2 * 2
h = np.frombuffer(d[:n2].tobytes(), dtype="<u2")
addrs2 = base + np.arange(len(h), dtype=np.uint64) * 2
sel = np.nonzero((h >> 11) == 0b01001)[0]
print("Thumb pc-relative LDR count:", len(sel))
th = 0
for i in sel:
    a = int(addrs2[i])
    pc = ((a + 4) & ~2)
    t = pc + int(h[i] & 0xFF) * 4
    for tg in targets:
        if abs(t - tg) <= 0x40:
            print(f"THMB {a:#x}: ldr r{(h[i] >> 8) & 7}, [pc, #{(h[i] & 0xFF) * 4:#x}] -> {t:#x}  (sbox {tg:#x})")
            th += 1
print("Thumb hits", th)
