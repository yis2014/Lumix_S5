"""Scan a Lumix S5 RAM dump for the firmware AES key.

Container format is the same UPD-v2 family the community documented for
GM1/GM5/GX9/GX8: per-section ciphertext, 32-byte plaintext SHA-256 and a
16-byte per-section IV slot. Cipher under test: AES-128-CBC, 5 rounds.

Filter is assumption-free: eep_ow_a and eep_ow_b have byte-identical
plaintext but different IVs, so for the right key both decrypt to the same
first block. A hit is then verified against loader1's stored SHA-256.
"""
import hashlib
import os
import struct
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ref"))
import key_test as K

BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", "S5___V29.bin")
DATA_OFF = 0x200
LEADIN = 0x200
ROUNDS = 5


def parse(data):
    recs = []
    off = 0x2EC
    while off + 0x5C <= len(data):
        name = data[off:off + 12].split(b"\0")[0]
        if not name or not all(32 <= c < 127 for c in name):
            break
        img, size, flash, flags = struct.unpack_from("<4I", data, off + 12)
        digest = data[off + 0x1C:off + 0x3C]
        iv = data[off + 0x3C:off + 0x4C]
        recs.append({"name": name.decode(), "img": img, "size": size,
                     "flags": flags, "digest": digest, "iv": iv})
        off += 0x5C
    return recs


def main():
    dump_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(BIN), "ram_80000000.bin")
    dump = open(dump_path, "rb").read()
    data = open(BIN, "rb").read()
    recs = {r["name"]: r for r in parse(data)}

    def stored(name):
        r = recs[name]
        off = DATA_OFF + r["img"]
        return data[off:off + r["size"]], r["iv"], r["digest"]

    ca, iva, _ = stored("eep_ow_a")
    cb, ivb, _ = stored("eep_ow_b")
    ca, cb = ca[:16], cb[:16]
    print("eep_ow_a block0:", ca.hex(), "iv", iva.hex())
    print("eep_ow_b block0:", cb.hex(), "iv", ivb.hex())
    print("dump:", len(dump), "bytes")

    xa = bytes(ca[i] ^ iva[i] for i in range(16))
    xb = bytes(cb[i] ^ ivb[i] for i in range(16))

    t0 = time.time()
    hits = []
    n = 0
    for pos in range(0, len(dump) - 16, 4):
        key = dump[pos:pos + 16]
        if key.count(key[0]) == 16:
            continue
        n += 1
        try:
            rk = K._key_expansion(key, ROUNDS)
            da = K.aes_decrypt_block(ca, rk, ROUNDS)
            db = K.aes_decrypt_block(cb, rk, ROUNDS)
        except Exception:
            continue
        if all((da[i] ^ iva[i]) == (db[i] ^ ivb[i]) for i in range(16)):
            hits.append((pos, key))
            print("CANDIDATE at dump+0x%X: %s" % (pos, key.hex()), flush=True)
        if n % 20000 == 0:
            print("  scanned %d (%.0fs, %.0f/s)" % (n, time.time() - t0, n / (time.time() - t0)), flush=True)

    print("scanned %d candidates in %.1fs, %d hit(s)" % (n, time.time() - t0, len(hits)))

    # verify each hit against loader1 (and any other section) full digest
    l1, iv1, dg1 = stored("loader1")
    for pos, key in hits:
        pt = K.decrypt_cbc(l1, key, ROUNDS, iv1)
        ok = hashlib.sha256(pt).digest() == dg1
        print("verify 0x%X %s -> %s" % (pos, key.hex(), "LOADER1 MATCH" if ok else "no"))
        if ok:
            print("KEY =", key.hex())
            open(os.path.join(os.path.dirname(BIN), "key.txt"), "w").write(key.hex() + "\n")


if __name__ == "__main__":
    main()
