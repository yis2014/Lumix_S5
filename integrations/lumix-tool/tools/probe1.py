import hashlib
import struct
import sys
from collections import Counter

b = open(r"out\S5___V29.bin", "rb").read()
HDR = 0x200
PAN = b[0x220:0x240]
print("panasonic field:", PAN.hex())

cands = {
    "whole file": b,
    "0x200:": b[0x200:],
    "0x2a0:": b[0x2a0:],
    "0x2a0:end": b[0x2a0:],
    "0x142c:end": b[0x142c:],
    "0x1600:end": b[0x1600:],
    "header 0x0:0x200": b[:0x200],
    "table 0x2ec:0x142c": b[0x2ec:0x142C],
    "data 0x1600:0x560ee00": b[0x1600:],
}
for k, v in cands.items():
    if hashlib.sha256(v).digest() == PAN:
        print("MATCH sha256", k)
print("crc32 whole:", hex(__import__("zlib").crc32(b)))
print("crc32 0x2a0:end:", hex(__import__("zlib").crc32(b[0x2a0:])))
print("crc32 data:", hex(__import__("zlib").crc32(b[0x1600:])))
print()

# ECB block repetition per blob
recs = []
off = 0x2EC
while off + 0x5C <= len(b):
    nm = b[off:off + 12].split(b"\0")[0]
    if not nm or not all(32 <= c < 127 for c in nm):
        break
    f1, f2, f3, fl = struct.unpack_from("<4I", b, off + 12)
    recs.append((nm.decode(), f1, f2, f3, fl, b[off + 0x1C:off + 0x3C], b[off + 0x3C:off + 0x4C]))
    off += 0x5C

cur = 0x1600
print("%-12s %-6s %8s  uniq16  maxrep  dup%%" % ("name", "flags", "size"))
for nm, f1, f2, f3, fl, h, iv in recs:
    blob = b[cur:cur + f2]
    blocks = [blob[i:i + 16] for i in range(0, len(blob) - 15, 16)]
    c = Counter(blocks)
    dup = sum(v for v in c.values() if v > 1)
    print("%-12s %-6d %8x  %6d  %6d  %5.1f%%" % (nm, fl, f2, len(c), max(c.values()) if c else 0, 100.0 * dup / max(1, len(blocks))))
    cur += f2
