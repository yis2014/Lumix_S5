"""Offline scan of high-memory dumps (0x90000000+) for bootloader/postboot traces.

Looks for AES tables, P-256 constants, ARM exception vectors, boot strings and
maps non-padding density per MiB to locate real code/data regions.
"""
import os

import numpy as np

FILES = [
    (r"E:\desktop\LUMIX\highmem_9000_a000.bin", 0x90000000),
    (r"E:\desktop\LUMIX\highmem_9000_9800.bin", 0x90000000),
]

PATTERNS = [
    ("AES S-box", bytes.fromhex("637c777bf26b6fc5")),
    ("AES inv S-box", bytes.fromhex("52096ad53036a538")),
    ("P-256 p (BE)", bytes.fromhex("ffffffff000000010000000000000000")),
    ("P-256 p (LE)", bytes.fromhex("000000000000000001000000ffffffff")),
    ("ARM vec ldr pc", bytes.fromhex("18f09fe5")),
    ("postboot", b"postboot"),
    ("POSTBOOT", b"POSTBOOT"),
    ("ECDSA", b"ECDSA"),
    ("P-256", b"P-256"),
    ("UPD", b"UPD"),
    ("LENS-UPDATE", b"LENS-UPDATE"),
    ("SMP/Cortex", b"SMP/Cortex"),
]


def scan(path, base):
    print(f"\n########## {os.path.basename(path)} (base {base:#x}) ##########")
    d = open(path, "rb").read()
    print(f"size = {len(d)} bytes ({len(d)/1e6:.1f} MB), end = {base+len(d):#x}")
    for name, pat in PATTERNS:
        hits = []
        start = 0
        while len(hits) < 8:
            i = d.find(pat, start)
            if i < 0:
                break
            hits.append(base + i)
            start = i + 1
        if hits:
            print(f"  {name:16s}: {[hex(h) for h in hits]}")

    a = np.frombuffer(d, dtype=np.uint8)
    mib = 1 << 20
    nblk = len(a) // mib
    print("  --- per-MiB density (not 00/55/FF), blocks >1% ---")
    for i in range(nblk):
        blk = a[i * mib:(i + 1) * mib]
        live = np.count_nonzero((blk != 0) & (blk != 0x55) & (blk != 0xFF))
        if live > mib // 100:
            print(f"    {base + i*mib:#x}: {live*100//mib}% live")


if __name__ == "__main__":
    for p, b in FILES:
        if os.path.exists(p):
            scan(p, b)
        else:
            print("missing:", p)
