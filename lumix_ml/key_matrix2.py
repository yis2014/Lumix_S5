import base64

import numpy as np
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

F = open(r"E:\desktop\LUMIX\S5___V29.bin", "rb").read()
PT = open(r"E:\desktop\LUMIX\program_0x86280000.bin", "rb").read()
REG = open(r"E:\desktop\LUMIX\keyregion.bin", "rb").read()

BLOB = REG[0x88:0x88 + 64]
DEC = base64.b64decode(BLOB)
print("blob", BLOB)
print("decoded", DEC.hex())

keys = {}
for i in range(4):
    keys[f"a128_{i}"] = BLOB[i * 16:(i + 1) * 16]
for i in range(2):
    keys[f"a256_{i}"] = BLOB[i * 32:(i + 1) * 32]
keys["b128"] = DEC[:16]
keys["b256_0"] = DEC[:32]
keys["b256_1"] = DEC[16:48]
keys["b128_1"] = DEC[16:32]
keys["b128_2"] = DEC[32:48]

CT = F[97280 + 0x200:97280 + 0x200 + 64]
IV = F[97280:97280 + 0x200][0x80:0x90]
TGT = {o: PT[o:o + 16] for o in (0, 0x200, 0x1000)}


def inv32(b):
    return (~np.frombuffer(b, dtype="<u4")).tobytes()


hits = 0
for kn, key in keys.items():
    for mn, mode in (("ctr", modes.CTR(IV)), ("cbc", modes.CBC(IV)),
                     ("ecb", modes.ECB()), ("ctr0", modes.CTR(bytes(16)))):
        try:
            out = Cipher(algorithms.AES(key), mode).decryptor().update(CT)
        except Exception as e:
            continue
        for var, dd in (("raw", out), ("inv", inv32(out))):
            for off, tgt in TGT.items():
                if dd[:16] == tgt:
                    print(f"*** HIT key={kn} mode={mn} {var} pt_off={off:#x} key={key!r}")
                    hits += 1
print("tested", len(keys), "keys; hits:", hits)
