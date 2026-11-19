"""Find code that references the AES tables in the S5 main-core image.

The AES S-box lives at phys 0x86f50454 (virt 0x06f50454) and the inverse S-box at
phys 0x86f50554. Any literal pointer to these is an AES encrypt/decrypt routine;
from there we walk up to the key schedule and its key source.
"""
import struct
import sys

from thumb_calls import disasm, find_callers

BIN = r"E:\desktop\LUMIX\program_0x86280000.bin"
BASE = 0x86280000
DELTA = 0x80000000

blob = open(BIN, "rb").read()


def refs_to_virt(virt, window=0):
    hits = []
    lo, hi = virt - window, virt + window + 1
    for off in range(0, len(blob) - 4, 4):
        v = struct.unpack_from("<I", blob, off)[0]
        if lo <= v < hi:
            hits.append(BASE + off)
    return hits


def main():
    targets = {
        "AES_Sbox": 0x06F50454,
        "AES_invSbox": 0x06F50554,
        "SHA256_init": 0x068C34DC,
    }
    for name, virt in targets.items():
        hits = refs_to_virt(virt)
        print(f"\n===== {name} virt 0x{virt:08x}: {len(hits)} literal refs =====")
        for h in hits[:6]:
            print(f"  literal @ phys 0x{h:08x}")
            print(disasm(blob, h - 0x50, 0x50))


if __name__ == "__main__":
    main()
