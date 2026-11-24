"""Fast Thumb-2 BL target scanner (pure arithmetic, no disassembler)."""
import struct
import sys


def bl_target(hw1, hw2, pc):
    if (hw1 & 0xF800) != 0xF000:
        return None
    if (hw2 & 0xD000) != 0xD000 or (hw2 & 0x1000) == 0:
        return None
    s = (hw1 >> 10) & 1
    imm10 = hw1 & 0x3FF
    j1 = (hw2 >> 13) & 1
    j2 = (hw2 >> 11) & 1
    i1 = 1 - (j1 ^ s)
    i2 = 1 - (j2 ^ s)
    imm = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | ((hw2 & 0x7FF) << 1)
    if s:
        imm -= 1 << 25
    return pc + 4 + imm


def main():
    path, target_str = sys.argv[1], sys.argv[2]
    target = int(target_str, 16)
    data = open(path, "rb").read()
    base = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0
    hits = []
    for off in range(0, len(data) - 4, 2):
        hw1 = struct.unpack_from("<H", data, off)[0]
        if (hw1 & 0xF800) != 0xF000:
            continue
        hw2 = struct.unpack_from("<H", data, off + 2)[0]
        t = bl_target(hw1, hw2, base + off)
        if t == target:
            hits.append(base + off)
    print("target 0x%X: %d call sites" % (target, len(hits)))
    for h in hits:
        print("  0x%X" % h)


if __name__ == "__main__":
    main()
