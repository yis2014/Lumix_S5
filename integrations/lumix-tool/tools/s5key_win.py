"""Scan windows around AES table locations in the S5 RAM dump for the key.

Filter (assumption-free): eep_ow_a and eep_ow_b have identical plaintext but
different IVs, so the right key makes their first CBC blocks decrypt equal.
A hit is verified against loader1's stored SHA-256.
"""
import hashlib
import os
import struct
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ref"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import key_test as K

BIN = os.path.join(ROOT, "out", "S5___V29.bin")
DUMP = os.path.join(ROOT, "archive", "DERIVED", "ram_0x80000000_0x83000000.bin")
BASE = 0x80000000
ROUNDS = 5

SITES = [0x80FCB5E0, 0x8171984A, 0x817435E0, 0x81BB112E, 0x81BCAF00]
WINDOW = 0x20000  # +/- 128 KiB


def load_sections():
    data = open(BIN, "rb").read()
    recs = {}
    off = 0x2EC
    while off + 0x5C <= len(data):
        name = data[off:off + 12].split(b"\0")[0]
        if not name or not all(32 <= c < 127 for c in name):
            break
        img, size, flash, flags = struct.unpack_from("<4I", data, off + 12)
        recs[name.decode()] = {
            "stored": data[0x200 + img:0x200 + img + size],
            "iv": data[off + 0x3C:off + 0x4C],
            "digest": data[off + 0x1C:off + 0x3C],
            "flags": flags,
        }
        off += 0x5C
    return recs


def main():
    dump = open(DUMP, "rb").read()
    recs = load_sections()
    ca = recs["eep_ow_a"]["stored"][:16]
    cb = recs["eep_ow_b"]["stored"][:16]
    iva = recs["eep_ow_a"]["iv"]
    ivb = recs["eep_ow_b"]["iv"]
    l1 = recs["loader1"]["stored"]
    l1iv = recs["loader1"]["iv"]
    l1dg = recs["loader1"]["digest"]

    t0 = time.time()
    hits = []
    n = 0
    for site in SITES:
        lo = max(0, site - BASE - WINDOW)
        hi = min(len(dump) - 16, site - BASE + WINDOW)
        print("window 0x%08X..0x%08X" % (BASE + lo, BASE + hi), flush=True)
        for pos in range(lo, hi, 4):
            key = dump[pos:pos + 16]
            if key.count(key[0]) == 16:
                continue
            n += 1
            rk = K._key_expansion(key, ROUNDS)
            da = K.aes_decrypt_block(ca, rk, ROUNDS)
            db = K.aes_decrypt_block(cb, rk, ROUNDS)
            if all((da[i] ^ iva[i]) == (db[i] ^ ivb[i]) for i in range(16)):
                print("CANDIDATE 0x%08X %s" % (BASE + pos, key.hex()), flush=True)
                hits.append((BASE + pos, key))
    print("scanned %d in %.1fs, %d hit(s)" % (n, time.time() - t0, len(hits)))
    for addr, key in hits:
        pt = K.decrypt_cbc(l1, key, ROUNDS, l1iv)
        ok = hashlib.sha256(pt).digest() == l1dg
        print("verify 0x%08X %s -> %s" % (addr, key.hex(), "LOADER1 MATCH" if ok else "no"))
        if ok:
            open(os.path.join(ROOT, "out", "key.txt"), "w").write(key.hex() + "\n")
            print("KEY =", key.hex())


if __name__ == "__main__":
    main()
