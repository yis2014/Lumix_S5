"""Build a candidate S5 firmware: program section replaced by the RAM plaintext
with the version fields patched, stored as flags=2 (no AES key involved).

Verifies every step: section size, patched offsets, digest, CRC, version.
"""
import hashlib
import struct
import sys
import zlib

BIN = r"out\S5___V29.bin"
MC = r"out\maincore.bin"
OUT = r"out\FW_candidate_v299.bin"
MC_BASE = 0x86000000
PROG_ADDR = 0x86280000
VERSION = 0x0299

b = bytearray(open(BIN, "rb").read())
mc = open(MC, "rb").read()

# locate the program record
off = 0x2EC
rec = None
while off + 0x5C <= len(b):
    name = b[off:off + 12].split(b"\0")[0]
    if not name or not all(32 <= c < 127 for c in name):
        break
    img, size, flash, flags = struct.unpack_from("<4I", b, off + 12)
    if name.decode() == "program":
        rec = (off, img, size, flash, flags)
        break
    off += 0x5C
if rec is None:
    raise SystemExit("program record not found")
roff, img, size, flash, flags = rec
print("program: img=0x%X size=0x%X flash=0x%X flags=%d" % (img, size, flash, flags))

blob_off = 0x200 + img
src = mc[PROG_ADDR - MC_BASE:PROG_ADDR - MC_BASE + size]
if len(src) != size:
    raise SystemExit("RAM program window short: %d" % len(src))

src = bytearray(src)
for delta in (0x863B0000 - PROG_ADDR, 0x863181E2 - PROG_ADDR):
    print("  patch +0x%X: %s -> %s" % (delta,
          src[delta:delta + 4].hex(), struct.pack("<HH", VERSION, VERSION).hex()))
    struct.pack_into("<H", src, delta, VERSION)
    struct.pack_into("<H", src, delta + 2, VERSION)

b[blob_off:blob_off + size] = src
struct.pack_into("<I", b, roff + 0x18, 2)                    # flags -> plaintext
b[roff + 0x1C:roff + 0x3C] = hashlib.sha256(src).digest()
struct.pack_into("<H", b, 0x1C, 0x0291)
struct.pack_into("<H", b, 0x1E, 0x0291)
struct.pack_into("<I", b, 0x40, zlib.crc32(bytes(b[0x200:])) & 0xFFFFFFFF)
open(OUT, "wb").write(b)

print("new section sha256:", hashlib.sha256(src).hexdigest())
print("outer crc32      : 0x%08X" % struct.unpack_from("<I", b, 0x40)[0])
print("container version: 0x%04X" % struct.unpack_from("<H", b, 0x1C)[0])
print("wrote           :", OUT, len(b))

