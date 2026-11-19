"""Offline crypto triage of the S5 main-core plaintext image.

Goal: locate the firmware-update signature verification path and any embedded
public keys, so we can either extract key material or patch the verifier.
"""
import re
import struct

BIN = r"E:\desktop\LUMIX\program_0x86280000.bin"
BASE = 0x86280000
DELTA = 0x80000000

blob = open(BIN, "rb").read()
N = len(blob)

CONSTANTS = {
    "SHA256_K": bytes.fromhex("982f8a427449a99165b5c0b8"),
    "SHA256_init_H0": bytes.fromhex("67e6096a85ae67bb72f36e3c"),
    "P256_prime": bytes.fromhex("ffffffff00000001000000000000000000000000ffffffffffffffffffffffff"),
    "P256_Gx": bytes.fromhex("6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296"),
    "P256_Gy": bytes.fromhex("4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5"),
    "P256_order": bytes.fromhex("ffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551"),
    "P384_prime_prefix": bytes.fromhex("fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffe"),
    "Curve25519_base": bytes.fromhex("0900000000000000000000000000000000000000000000000000000000000000"),
    "AES_Sbox": bytes.fromhex("637c777bf26b6fc53001672bfed7ab76"),
    "AES_invSbox": bytes.fromhex("52096ad53036a538bf40a39e81f3d7fb"),
    "MD5_init": bytes.fromhex("0123456789abcdeffedcba9876543210"),
    "SHA1_init": bytes.fromhex("67452301efcdab8998badcfe10325476"),
}

print("===== crypto constants =====")
for name, pat in CONSTANTS.items():
    hits = []
    start = 0
    while True:
        i = blob.find(pat, start)
        if i < 0:
            break
        hits.append(BASE + i)
        start = i + 4
        if len(hits) > 8:
            break
    if hits:
        print(f"{name:22s} @ {[hex(h) for h in hits]}")

print("\n===== update / signature related strings =====")
KEYWORDS = [b"UPD", b"signature", b"Signature", b"SIGN", b"verify", b"Verify", b"VERIFY",
            b"ECDSA", b"RSA", b"SHA256", b"sha256", b"SHA-256", b"certificate", b"Certificate",
            b"public key", b"PUBLIC KEY", b"decrypt", b"Decrypt", b"encrypt", b"firmware",
            b"Firmware", b"UPDATE", b"update.bin", b"auth", b"Auth", b"HASH", b"hash"]
seen = set()
for kw in KEYWORDS:
    for m in re.finditer(re.escape(kw), blob):
        off = m.start()
        # expand to full printable string
        s = off
        while s > 0 and 32 <= blob[s - 1] < 127:
            s -= 1
        e = off
        while e < N and 32 <= blob[e] < 127:
            e += 1
        text = blob[s:e].decode("ascii", "ignore")
        if len(text) < 4 or text in seen:
            continue
        seen.add(text)
        print(f"  0x{BASE+s:08x} (virt 0x{BASE+s-DELTA:08x}): {text[:110]}")
        if len(seen) > 120:
            break

print("\n===== UPD magic occurrences =====")
for m in re.finditer(b"UPD\x00", blob):
    print(f"  0x{BASE+m.start():08x} (virt 0x{BASE+m.start()-DELTA:08x})")

print("\n===== candidate public-key blobs (>=64B high entropy in rodata) =====")
# entropy heuristic over 64-byte windows in the first 20 MiB (rodata/code area)
import math
def ent(b):
    if not b:
        return 0.0
    from collections import Counter
    c = Counter(b)
    return -sum((v/len(b))*math.log2(v/len(b)) for v in c.values())

cand = []
i = 0
while i < min(N, 20 * 1024 * 1024) - 64:
    w = blob[i:i+64]
    if ent(w) > 5.7 and len(set(w)) > 45:
        cand.append(BASE + i)
        i += 64
    else:
        i += 16
print(f"{len(cand)} high-entropy 64B windows (first 20 shown)")
for a in cand[:20]:
    print(f"  0x{a:08x}: {blob[a-BASE:a-BASE+32].hex()}")
