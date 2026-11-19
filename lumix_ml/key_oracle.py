import sys

import numpy as np
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

F = open(r"E:\desktop\LUMIX\S5___V29.bin", "rb").read()
PT = open(r"E:\desktop\LUMIX\program_0x86280000.bin", "rb").read()
REGION = open(sys.argv[1], "rb").read()
BASE = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0

PROG_OFF = 97280 + 0x200
CT = F[PROG_OFF:PROG_OFF + 32]
IV_HDR = F[97280:97280 + 0x200][0x80:0x90]

TARGETS = {off: PT[off:off + 16] for off in (0, 0x200, 0x1000)}
print("target pt[0]:", TARGETS[0].hex())
print("iv hdr:", IV_HDR.hex())


def inv32(b):
    return (~np.frombuffer(b, dtype="<u4")).tobytes()


found = []
n = len(REGION) - 16
for i in range(n + 1):
    key = REGION[i:i + 16]
    for iv_name, iv in (("hdr", IV_HDR), ("zero", bytes(16))):
        dec = Cipher(algorithms.AES(key), modes.CTR(iv)).decryptor().update(CT)
        for variant, dd in (("raw", dec), ("inv", inv32(dec))):
            first = dd[:16]
            for off, tgt in TARGETS.items():
                if first == tgt:
                    print(f"*** KEY FOUND at {BASE + i:#x} iv={iv_name} {variant} pt_off={off:#x} key={key.hex()} ascii={key!r}")
                    found.append((BASE + i, key))
    if i % 4096 == 0:
        print(f"...{i}/{n}", flush=True)
print("done, found:", found)
