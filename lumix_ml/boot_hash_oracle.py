"""Two zero-cost checks against the resident low-RAM boot code:

1. Hash oracle: do any aligned windows of the RAM dumps match the known
   plaintext SHA-256 of loader1/2/3 (firmware_table.json h1)?
2. Locate partition-load code: scan lowmem for the load-address constants
   (program 0x86280000, rootfs1 0x83100000, rootfs2 0x83400000,
   zimage 0x80200000, stack 0x13000). Their references mark the code that
   decrypts+loads partitions - i.e. the bootloader's crypto path.
"""
import hashlib
import struct

import numpy as np

LOW = r"E:\desktop\LUMIX\lowmem_0_2M.bin"
BASE = 0x80000000
d = open(LOW, "rb").read()

LOADERS = [
    ("loader1", 4096, "e009d688fb152a70d90fb4df88705b29f441e3dc50c57e4ea1fddf1a49c19d32"),
    ("loader2", 38912, "4a925f2e019310a9a8f2029df652cc7a5e93be5fb8ee4b6b29c6c6d3805cea85"),
    ("loader3", 49152, "67d44d7c2bb2091b7a56ca5118345e0ee604e6b2c6c31769cd6de06ae752d838"),
]

print("===== 1. loader plaintext hash oracle =====")
for name, size, want in LOADERS:
    hits = []
    for off in range(0, len(d) - size, 0x100):
        if hashlib.sha256(d[off:off + size]).hexdigest() == want:
            hits.append(BASE + off)
    print(f"{name}: {'MATCH at ' + str([hex(h) for h in hits]) if hits else 'no exact window match'}")

print("\n===== 2. partition load-address constants in lowmem =====")
TARGETS = [0x86280000, 0x83100000, 0x83400000, 0x80200000,
           0x80208000, 0x822FF000, 0x80120800, 0x00013000, 0x80013000]
n = len(d) // 4 * 4
w = np.frombuffer(d[:n], dtype="<u4")
for t in TARGETS:
    idx = np.nonzero(w == t)[0]
    if len(idx):
        print(f"0x{t:08x}: {len(idx)} hit(s) at {[hex(BASE + int(i)*4) for i in idx[:12]]}")

print("\n===== 3. any 0x86/0x83/0x82-prefixed code-ish constants (top 40) =====")
from collections import Counter
sel = (w >= 0x80000000) & (w < 0x90000000)
c = Counter(int(v) for v in w[sel])
shown = 0
for v in sorted(c):
    if c[v] >= 1 and (v & 0xFFF) != 0:  # skip page-aligned noise where possible
        pass
for v in sorted(c):
    if v in (0x80000000, 0x88000000):
        continue
    print(f"0x{v:08x} x{c[v]}")
    shown += 1
    if shown >= 40:
        break
