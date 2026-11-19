"""Scan for movw/movt immediate pairs that materialise a given address in Thumb-2."""
import struct
import sys

from thumb_calls import disasm

BIN = r"E:\desktop\LUMIX\program_0x86280000.bin"
BASE = 0x86280000
blob = open(BIN, "rb").read()


def mov_patterns(value, movt=False):
    """Yield (hw1, hw2) encodings for movw/movt rD, #imm16 for every register."""
    imm16 = value & 0xFFFF
    imm4 = (imm16 >> 12) & 0xF
    i = (imm16 >> 11) & 1
    imm3 = (imm16 >> 8) & 0x7
    imm8 = imm16 & 0xFF
    base = 0xF2C0 if movt else 0xF240
    hw1 = base | (i << 10) | imm4
    for rd in range(15):
        hw2 = (imm3 << 12) | (rd << 8) | imm8
        yield rd, struct.pack("<HH", hw1, hw2)


def scan(value):
    hits = []
    for rd, pat in mov_patterns(value, movt=False):
        start = 0
        while True:
            i = blob.find(pat, start)
            if i < 0:
                break
            hits.append((BASE + i, rd))
            start = i + 2
    return hits


def main():
    for arg in sys.argv[1:]:
        value = int(arg, 0)
        hits = scan(value)
        print(f"\n=== movw #0x{value & 0xFFFF:04x} (of 0x{value:08x}): {len(hits)} sites ===")
        for addr, rd in hits[:10]:
            print(f"  @ phys 0x{addr:08x} r{rd}")
            print(disasm(blob, addr - 0x10, 0x30))


if __name__ == "__main__":
    main()
