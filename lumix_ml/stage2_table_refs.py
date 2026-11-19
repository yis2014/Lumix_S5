"""Find code references to the static video/bitrate table at 0x86a077e4."""
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
from thumb_calls import disasm

BIN = r"E:\desktop\LUMIX\program_0x86280000.bin"
BASE = 0x86280000          # physical load address of the dump
VIRT_DELTA = 0x80000000    # main core virtual = physical - 0x80000000
TABLE = 0x86A077E4
END = TABLE + 15 * 0x74
VTABLE = TABLE - VIRT_DELTA
VEND = END - VIRT_DELTA


def main():
    with open(BIN, "rb") as f:
        blob = f.read()

    hits = {}
    for off in range(0, len(blob) - 4, 4):
        v = struct.unpack_from("<I", blob, off)[0]
        if VTABLE - 0x400 <= v < VEND + 0x400:
            hits.setdefault(v, []).append(BASE + off)

    print(f"{len(hits)} distinct virtual pointers near the table")
    for v in sorted(hits):
        locs = hits[v]
        tag = "IN-TABLE" if VTABLE <= v < VEND else "nearby"
        print(f"\n=== virtual 0x{v:08x} (physical 0x{v+VIRT_DELTA:08x}, table+0x{v-VTABLE:x}) [{tag}] at {[hex(x) for x in locs][:4]} ===")
        for loc in locs[:2]:
            # literal pools sit right after the code that uses them; scan backwards
            print(disasm(blob, loc - 0x60, 0x60))


if __name__ == "__main__":
    main()
