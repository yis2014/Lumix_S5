import sys

import numpy as np

path, base = sys.argv[1], int(sys.argv[2], 16)
targets = {int(x, 16) for x in sys.argv[3:]}
d = np.frombuffer(open(path, "rb").read(), dtype=np.uint8)
n = len(d) // 2 * 2
h = np.frombuffer(d[:n].tobytes(), dtype="<u2")

h1 = h[:-1].astype(np.uint32)
h2 = h[1:].astype(np.uint32)
mask = ((h1 & 0xF800) == 0xF000) & ((h2 & 0xD000) == 0xD000) & ((h2 & 0x1000) != 0)
idx = np.nonzero(mask)[0]
print("BL candidates:", len(idx))

for i in idx:
    a1 = int(h1[i])
    a2 = int(h2[i])
    S = (a1 >> 10) & 1
    imm10H = a1 & 0x3FF
    J1 = (a2 >> 13) & 1
    J2 = (a2 >> 11) & 1
    imm10L = a2 & 0x3FF
    I1 = 1 - (J1 ^ S)
    I2 = 1 - (J2 ^ S)
    imm = (S << 24) | (I1 << 23) | (I2 << 22) | (imm10H << 12) | (imm10L << 1)
    if S:
        imm -= 1 << 25
    a = base + int(i) * 2
    t = (a + 4 + imm) & 0xFFFFFFFF
    if t in targets or (t & ~1) in targets:
        print(f"caller {a:#x} -> {t:#x}", flush=True)
print("done")
