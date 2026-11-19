"""Search the S5 main-core image for the recovered metadata public key and P-256 params.

Previous work recovered the metadata ECDSA public key but could not scan the S5
program (it had not been dumped yet). Now we can point straight at the verifier.
"""
import struct

BIN = r"E:\desktop\LUMIX\program_0x86280000.bin"
BASE = 0x86280000
DELTA = 0x80000000
blob = open(BIN, "rb").read()

_raw = open(r"E:\desktop\LUMIX\analysis\eeprom_keyhunt_20261101\metadata_public_recovery\S5_V28_V29_metadata_public_0ffaf83e958b_raw64_BE.bin", "rb").read()
PUB_X = _raw[:32].hex()
PUB_Y = _raw[32:].hex()
P256 = {
    "prime": "ffffffff00000001000000000000000000000000ffffffffffffffffffffffff",
    "Gx": "6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296",
    "Gy": "4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5",
    "order": "ffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551",
}


def variants(b):
    out = {"BE": b, "BE_reversed": b[::-1]}
    # per-u32 little-endian words, same word order
    out["LE_words"] = b"".join(b[i:i + 4][::-1] for i in range(0, len(b), 4))
    # full little-endian scalar: reverse word order AND bytes in each word
    words = [b[i:i + 4][::-1] for i in range(0, len(b), 4)]
    out["LE_full"] = b"".join(words[::-1])
    return out


def hunt(name, hexstr):
    raw = bytes.fromhex(hexstr)
    for vn, pat in variants(raw).items():
        start = 0
        while True:
            i = blob.find(pat, start)
            if i < 0:
                break
            print(f"  HIT {name}/{vn} @ phys 0x{BASE+i:08x} (virt 0x{BASE+i-DELTA:08x})")
            start = i + 4
        # also try 16-byte half patterns for long constants
    # short prefix search to catch split storage
    for vn, pat in variants(raw).items():
        p = pat[:16]
        start = 0
        while True:
            i = blob.find(p, start)
            if i < 0:
                break
            print(f"  prefix16 {name}/{vn} @ phys 0x{BASE+i:08x}")
            start = i + 4


print("=== S5 metadata public key X ===")
hunt("pubX", PUB_X)
print("=== S5 metadata public key Y ===")
hunt("pubY", PUB_Y)
for name, h in P256.items():
    print(f"=== P-256 {name} ===")
    hunt(name, h)
print("done")
