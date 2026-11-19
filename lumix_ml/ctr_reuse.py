import math
import re

import numpy as np

F = open(r"E:\desktop\LUMIX\S5___V29.bin", "rb").read()
PT = open(r"E:\desktop\LUMIX\program_0x86280000.bin", "rb").read()

PARTS = {
    "program": (97280 + 0x200, 16674816),
    "postboot1": (16772096 + 0x200, 4718592),
    "music": (32117760 + 0x200, 3538944),
    "loader2": (9216 + 0x200, 38912),
}


def entropy(b):
    if not b:
        return 0.0
    c = np.bincount(np.frombuffer(b, dtype=np.uint8), minlength=256) / len(b)
    c = c[c > 0]
    return float(-(c * np.log2(c)).sum())


prog_ct = np.frombuffer(F[PARTS["program"][0]:PARTS["program"][0] + PARTS["program"][1]], dtype=np.uint8)
print("program ct", len(prog_ct))

for pt_off in (0, 0x200, 0x1000):
    pt = np.frombuffer(PT[pt_off:pt_off + len(prog_ct)], dtype=np.uint8)
    if len(pt) < len(prog_ct):
        continue
    ks = prog_ct ^ pt
    for name, (off, size) in PARTS.items():
        if name == "program":
            continue
        ct = np.frombuffer(F[off:off + size], dtype=np.uint8)
        dec = ct ^ ks[:len(ct)]
        b = dec[:65536].tobytes()
        strs = [s.decode() for s in re.findall(rb"[ -~]{8,}", b)][:5]
        print(f"pt_off={pt_off:#x} {name}: entropy={entropy(b):.3f} head={b[:16].hex()} strs={strs}")
