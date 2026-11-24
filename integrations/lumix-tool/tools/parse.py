import hashlib
import struct
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else r"out\S5___V29.bin"
b = open(PATH, "rb").read()
REC = 0x5C


def rec_fields(off):
    name = b[off:off + 12].split(b"\0")[0].decode("latin-1")
    f1, f2, f3, flags = struct.unpack_from("<4I", b, off + 12)
    h = b[off + 0x1C:off + 0x3C]
    iv = b[off + 0x3C:off + 0x4C]
    rsv = b[off + 0x4C:off + 0x5C]
    return name, f1, f2, f3, flags, h, iv, rsv


def walk(start):
    off = start
    out = []
    while off + REC <= len(b):
        name = b[off:off + 12].split(b"\0")[0]
        if not name or not all(32 <= c < 127 for c in name):
            break
        out.append((off,) + rec_fields(off))
        off += REC
    return out


for label, start in (("outer", 0x200), ("inner", 0x2EC)):
    recs = walk(start)
    print("=== %s table at 0x%x: %d records ===" % (label, start, len(recs)))
    for off, name, f1, f2, f3, flags, h, iv, rsv in recs:
        # interpret f3 as file offset, f2 as length
        ok = None
        if f3 + f2 <= len(b):
            ok = hashlib.sha256(b[f3:f3 + f2]).digest() == h
        print("%08x %-12s f1=%08x f2=%08x f3=%08x flags=%d hashok=%-5s iv=%s rsv0=%s"
              % (off, name, f1, f2, f3, flags, ok, iv.hex()[:16], rsv == b"\0" * 16))
    print()
