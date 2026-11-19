import sys

import numpy as np

path, base, target = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
d = np.frombuffer(open(path, "rb").read(), dtype=np.uint8)
n = len(d) // 2 * 2
h = np.frombuffer(d[:n].tobytes(), dtype="<u2")

for i in range(len(h) - 1):
    h1 = int(h[i])
    h2 = int(h[i + 1])
    if (h1 & 0xF800) != 0xF000:
        continue
    if (h2 & 0xD000) != 0xD000:
        continue
    is_blx = (h2 & 0x1000) == 0
    if is_blx:
        continue
    S = (h1 >> 10) & 1
    imm10H = h1 & 0x3FF
    J1 = (h2 >> 13) & 1
    J2 = (h2 >> 11) & 1
    imm10L = h2 & 0x3FF
    I1 = 1 - (J1 ^ S)
    I2 = 1 - (J2 ^ S)
    imm = (S << 24) | (I1 << 23) | (I2 << 22) | (imm10H << 12) | (imm10L << 1)
    if S:
        imm -= 1 << 25
    a = base + i * 2
    t = (a + 4 + imm) & 0xFFFFFFFF
    if t == target or t == (target | 1):
        print(f"caller at {a:#x}: bl {t:#x}")
