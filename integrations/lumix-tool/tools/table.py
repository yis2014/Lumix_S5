import struct, sys, re

path = sys.argv[1] if len(sys.argv) > 1 else r"out\S5___V29.bin"
b = open(path, "rb").read()
lo, hi = (int(sys.argv[2], 0), int(sys.argv[3], 0)) if len(sys.argv) > 3 else (0, 0x2000)

names = []
i = lo
while i < hi:
    j = i
    while j < len(b) and 32 <= b[j] < 127:
        j += 1
    if j - i >= 4 and j < len(b) and b[j] == 0 and (i == 0 or b[i - 1] == 0):
        names.append((i, b[i:j].decode("ascii")))
        i = j
    else:
        i += 1

print("name offsets and deltas")
prev = None
for off, nm in names:
    d = "" if prev is None else "d=+0x%x" % (off - prev)
    print("%08x  %-14s %s" % (off, nm, d))
    prev = off
print()

for off, nm in names[:40]:
    blk = b[off:off + 0x60]
    u = struct.unpack("<24I", blk)
    print("== %08x %s" % (off, nm))
    print("   " + " ".join("%08x" % x for x in u))
