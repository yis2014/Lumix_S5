"""Static analysis (offline, no camera I/O): find how the bitrate logger gets its object.

The logger at 0x8775c210 prints "TSTargetBitrate = %d, TSMaxBitrate = %d, TSMinBitrate = %d"
using fields at +0x28/+0x2c/+0x30 of some object. If we can recover where that object
pointer comes from (a global pointer / singleton), we get the LIVE runtime address of
the bitrate settings instead of guessing from the static table.
"""
import struct
import sys

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

BIN = r"E:\desktop\LUMIX\program_0x86280000.bin"
BASE = 0x86280000
FUNC = 0x8775C210
FMT = 0x8775C609
SIZE = 0x400


def u32(b, off):
    return struct.unpack_from("<I", b, off)[0]


def main():
    with open(BIN, "rb") as f:
        blob = f.read()

    # 1) Where is the format-string address referenced as a literal?
    needle = struct.pack("<I", FMT)
    hits = []
    start = 0
    while True:
        i = blob.find(needle, start)
        if i < 0:
            break
        hits.append(BASE + i)
        start = i + 4
    print(f"literal references to fmt 0x{FMT:08x}: {[hex(h) for h in hits]}")

    # 2) Disassemble the logger window in both ARM and Thumb and report
    off = FUNC - BASE
    code = blob[off:off + SIZE]
    for name, mode in (("ARM", CS_MODE_ARM), ("THUMB", CS_MODE_THUMB)):
        md = Cs(CS_ARCH_ARM, mode | CS_MODE_LITTLE_ENDIAN)
        md.detail = False
        print(f"\n===== {name} @ 0x{FUNC:08x} =====")
        for ins in md.disasm(code, FUNC):
            print(f"0x{ins.address:08x}: {ins.mnemonic:10s} {ins.op_str}")
            if ins.address > FUNC + 0x180:
                break

    # 3) Any literal-pool words inside the function window that look like RAM pointers?
    print("\n===== literal-pool candidates in function window (0x8xxxxxxx) =====")
    for i in range(0, SIZE, 4):
        v = u32(code, i)
        if 0x86000000 <= v <= 0x9FFFFFFF and v % 4 == 0:
            print(f"  +0x{i:03x} (0x{FUNC+i:08x}) -> 0x{v:08x}")


if __name__ == "__main__":
    main()
