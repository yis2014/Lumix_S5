"""Scan Thumb-2 movw/movt pairs that materialise addresses inside the video table."""
import struct

from thumb_calls import disasm

BIN = r"E:\desktop\LUMIX\program_0x86280000.bin"
BASE = 0x86280000
TABLE = 0x86A077E4
END = TABLE + 15 * 0x74
WINDOW = 0x400  # also accept references to nearby structs


def decode_mov(hw1, hw2):
    """Return (kind, rd, imm16) for movw/movt, else None."""
    if (hw1 & 0xFBF0) == 0xF240:
        kind = "movw"
    elif (hw1 & 0xFBF0) == 0xF2C0:
        kind = "movt"
    else:
        return None
    i = (hw1 >> 10) & 1
    imm4 = hw1 & 0xF
    imm3 = (hw2 >> 12) & 0x7
    rd = (hw2 >> 8) & 0xF
    imm8 = hw2 & 0xFF
    imm16 = (imm4 << 12) | (i << 11) | (imm3 << 8) | imm8
    return kind, rd, imm16


def main():
    with open(BIN, "rb") as f:
        blob = f.read()

    lows = {}   # rd -> list of (addr, imm16)
    found = []
    for off in range(0, len(blob) - 4, 2):
        hw1, hw2 = struct.unpack_from("<HH", blob, off)
        d = decode_mov(hw1, hw2)
        if not d:
            continue
        kind, rd, imm16 = d
        addr = BASE + off
        if kind == "movw":
            lows.setdefault(rd, []).append((addr, imm16))
        else:  # movt gives the high half: high = imm16
            high = imm16 << 16
            if not (0x86000000 <= high <= 0x9F000000):
                continue
            for a_low, lo in lows.get(rd, [])[-3:]:
                full = high | lo
                if TABLE - WINDOW <= full < END + WINDOW:
                    found.append((full, a_low, addr, rd))

    print(f"{len(found)} candidate address materialisations near the table")
    seen = set()
    for full, a_low, a_high, rd in found:
        if full in seen:
            continue
        seen.add(full)
        tag = "IN-TABLE" if TABLE <= full < END else "nearby"
        print(f"\n=== 0x{full:08x} [{tag}] movw@0x{a_low:08x} movt@0x{a_high:08x} (r{rd}) ===")
        print(disasm(blob, a_low - 0x30, 0x60))


if __name__ == "__main__":
    main()
