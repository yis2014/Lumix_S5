import base64

import numpy as np
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

F = open(r"E:\desktop\LUMIX\S5___V29.bin", "rb").read()
PT = open(r"E:\desktop\LUMIX\program_0x86280000.bin", "rb").read()

REG = open(r"E:\desktop\LUMIX\keyregion.bin", "rb").read()
start = 0x88
end = start
while end < len(REG) and REG[end] in b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=":
    end += 1
BLOB = REG[start:end]
print("blob len", len(BLOB), BLOB)

cands = {}
for i in range(len(BLOB) // 16):
    cands[f"ascii_seg{i}"] = BLOB[i * 16:(i + 1) * 16]
try:
    dec = base64.b64decode(BLOB[:len(BLOB) // 4 * 4])
except Exception as e:
    print("b64 fail", e)
    dec = b""
print("b64 decoded len", len(dec), dec.hex())
for i in range(0, len(dec) - 15, 16):
    cands[f"b64_{i}"] = dec[i:i + 16]
cands["b64_first16"] = dec[:16]

PROG_OFF = 97280 + 0x200
CT = F[PROG_OFF:PROG_OFF + 64]
HDR = F[97280:97280 + 0x200]
ivs = {"zero": bytes(16), "hdr80": HDR[0x80:0x90]}
for off in (0x70, 0x90, 0xA0, 0x60):
    ivs[f"hdr{off:x}"] = HDR[off:off + 16]

TGT = {o: PT[o:o + 16] for o in (0, 0x200, 0x1000)}


def inv32(b):
    return (~np.frombuffer(b, dtype="<u4")).tobytes()


hits = 0
for kn, key in cands.items():
    if len(key) != 16:
        continue
    for ivn, iv in ivs.items():
        out = Cipher(algorithms.AES(key), modes.CTR(iv)).decryptor().update(CT)
        for var, dd in (("raw", out), ("inv", inv32(out))):
            for off, tgt in TGT.items():
                if dd[:16] == tgt:
                    print(f"*** HIT key={kn} ({key!r}) iv={ivn} {var} pt_off={off:#x}")
                    hits += 1
print("candidates:", len(cands), "hits:", hits)
