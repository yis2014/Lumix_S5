"""Lumix S5 update-container (UPD) reader / patcher.

Format recovered from S5___V29.bin (see notes/FORMAT.md).

  outer header 0x000..0x1FF   magic "UPD\0", model "MC801"
  outer table  0x200          1 record ("panasonic"), 0x5C bytes
  inner header 0x2A0          0x4C bytes, copy of outer header + 12-byte tail
  inner table  0x2EC          N x 0x5C records
  data area    0x200 + min(addr)

Record (0x5C):
  +0x00 name[12]
  +0x0C u32 img_off     offset inside the decrypted image (contiguous)
  +0x10 u32 size        blob length (same in image and on flash)
  +0x14 u32 flash_off   destination address on flash
  +0x18 u32 flags       2 = plaintext, 3 = encrypted
  +0x1C sha256[32]      digest of the *plaintext*
  +0x3C iv[16]          per-record IV (zero when flags == 2)
  +0x4C [16]            zero

Container-level checks:
  +0x3C u32  payload size (0x560EC00)
  +0x40 u32  CRC32 over container[0x200:]        (recomputable)
  +0x220[32] unknown digest, NOT any plain hash we tried  (see notes)

Usage:
  python tools/lumixupd.py list      <bin>
  python tools/lumixupd.py verify    <bin>
  python tools/lumixupd.py extract   <bin> <name> <out>
  python tools/lumixupd.py set-flash <bin> <name> <hexaddr> <out>
"""
import hashlib
import struct
import sys
import zlib

OUTER_HDR = 0x200
INNER_HDR = 0x2A0
INNER_TBL = 0x2EC
REC = 0x5C
CRC_OFF = 0x40
CRC_START = 0x200


def load(path):
    with open(path, "rb") as f:
        return bytearray(f.read())


def records(b):
    out = []
    off = INNER_TBL
    while off + REC <= len(b):
        raw = bytes(b[off:off + 12])
        name = raw.split(b"\0")[0]
        if not name or not all(32 <= c < 127 for c in name):
            break
        img_off, size, flash_off, flags = struct.unpack_from("<4I", b, off + 0x0C)
        out.append({
            "off": off,
            "name": name.decode(),
            "img_off": img_off,
            "size": size,
            "flash": flash_off,
            "flags": flags,
            "sha": bytes(b[off + 0x1C:off + 0x3C]),
            "iv": bytes(b[off + 0x3C:off + 0x4C]),
        })
        off += REC
    return out


def data_start(b):
    recs = records(b)
    return OUTER_HDR + min(r["img_off"] for r in recs)


def blobs(b):
    cur = data_start(b)
    for r in records(b):
        yield r, b[cur:cur + r["size"]]
        cur += r["size"]


def fix_crc(b):
    struct.pack_into("<I", b, CRC_OFF, zlib.crc32(bytes(b[CRC_START:])) & 0xFFFFFFFF)


def cmd_list(path):
    b = load(path)
    print("size 0x%x   crc@0x3c=0x%08x (calc 0x%08x)"
          % (len(b), struct.unpack_from("<I", b, CRC_OFF)[0],
             zlib.crc32(bytes(b[CRC_START:])) & 0xFFFFFFFF))
    print("panasonic digest:", bytes(b[0x220:0x240]).hex())
    print()
    print("%-12s %10s %10s %10s %5s %s" % ("name", "img_off", "size", "flash", "fl", "sha256[0:8]"))
    for r in records(b):
        print("%-12s %10x %10x %10x %5d %s"
              % (r["name"], r["img_off"], r["size"], r["flash"], r["flags"], r["sha"][:8].hex()))


def cmd_verify(path):
    b = load(path)
    bad = 0
    for r, blob in blobs(b):
        if r["flags"] == 2:
            ok = hashlib.sha256(bytes(blob)).digest() == r["sha"]
            if not ok:
                bad += 1
            print("%-12s flags=2 sha256 match=%s" % (r["name"], ok))
        else:
            print("%-12s flags=3 encrypted, sha over plaintext (not checkable offline)" % r["name"])
    print("\nplaintext mismatches:", bad)


def cmd_extract(path, name, out):
    b = load(path)
    for r, blob in blobs(b):
        if r["name"] == name:
            with open(out, "wb") as f:
                f.write(blob)
            print("wrote %s (%d bytes, flags=%d)" % (out, len(blob), r["flags"]))
            return
    raise SystemExit("no such partition: " + name)


def cmd_set_flash(path, name, addr, out):
    b = load(path)
    for r in records(b):
        if r["name"] == name:
            old = r["flash"]
            struct.pack_into("<I", b, r["off"] + 0x14, addr)
            fix_crc(b)
            with open(out, "wb") as f:
                f.write(b)
            print("%s flash 0x%08x -> 0x%08x ; crc fixed ; wrote %s" % (name, old, addr, out))
            return
    raise SystemExit("no such partition: " + name)


def cmd_set_rsv(path, name, hexbytes, out):
    b = load(path)
    raw = bytes.fromhex(hexbytes)
    if len(raw) != 16:
        raise SystemExit("need exactly 16 bytes")
    for r in records(b):
        if r["name"] == name:
            b[r["off"] + 0x4C:r["off"] + 0x5C] = raw
            fix_crc(b)
            with open(out, "wb") as f:
                f.write(b)
            print("%s reserved[16] = %s ; crc fixed ; wrote %s" % (name, raw.hex(), out))
            return
    raise SystemExit("no such partition: " + name)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == "list":
        cmd_list(path)
    elif cmd == "verify":
        cmd_verify(path)
    elif cmd == "extract":
        cmd_extract(path, sys.argv[3], sys.argv[4])
    elif cmd == "set-flash":
        cmd_set_flash(path, sys.argv[3], int(sys.argv[4], 16), sys.argv[5])
    elif cmd == "set-rsv":
        cmd_set_rsv(path, sys.argv[3], sys.argv[4], sys.argv[5])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
