"""Repack an S5 update container without any AES key.

Takes an official container, replaces one section's stored blob with our own
plaintext of the same size, flips that section's flags to 2 (plaintext), fixes
the section's plaintext SHA-256, and recomputes the outer CRC32.  Optionally
bumps the container version field so the camera offers the update.

This is the "no key" path: flags==2 sections are stored in the clear and the
updater writes them as-is.

Usage:
  python tools/repack.py <in.bin> <out.bin> --section postboot5 --patch <file>
                         [--version 0x0291] [--expect-sha <hex>]
"""
import argparse
import hashlib
import struct
import zlib

DIR = 0x2EC
REC = 0x5C
DATA_BASE = 0x200
CRC_OFF = 0x40


def parse(data):
    recs = []
    off = DIR
    while off + REC <= len(data):
        name = data[off:off + 12].split(b"\0")[0]
        if not name or not all(32 <= c < 127 for c in name):
            break
        img, size, flash, flags = struct.unpack_from("<4I", data, off + 12)
        recs.append({
            "off": off, "name": name.decode(), "img": img, "size": size,
            "flash": flash, "flags": flags,
            "sha": data[off + 0x1C:off + 0x3C],
            "iv": data[off + 0x3C:off + 0x4C],
        })
        off += REC
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--section", required=True)
    ap.add_argument("--patch", required=True, help="plaintext file for the section")
    ap.add_argument("--version", default=None, help="new 0x1C version, e.g. 0x0291")
    ap.add_argument("--expect-sha", default=None,
                    help="refuse unless the current stored blob hashes to this")
    args = ap.parse_args()

    data = bytearray(open(args.inp, "rb").read())
    recs = parse(data)
    rec = next((r for r in recs if r["name"] == args.section), None)
    if rec is None:
        raise SystemExit("no such section: " + args.section)

    blob_off = DATA_BASE + rec["img"]
    old = bytes(data[blob_off:blob_off + rec["size"]])
    if args.expect_sha and hashlib.sha256(old).hexdigest() != args.expect_sha:
        raise SystemExit("stored blob hash mismatch; refusing")

    new = open(args.patch, "rb").read()
    if len(new) != rec["size"]:
        raise SystemExit("patch size %d != section size %d" % (len(new), rec["size"]))

    # sanity: the patch must be structurally plausible for this section
    data[blob_off:blob_off + rec["size"]] = new
    struct.pack_into("<I", data, rec["off"] + 0x18, 2)          # flags -> plaintext
    data[rec["off"] + 0x1C:rec["off"] + 0x3C] = hashlib.sha256(new).digest()
    if args.version is not None:
        v = int(args.version, 0)
        struct.pack_into("<H", data, 0x1C, v)
        struct.pack_into("<H", data, 0x1E, v)
    struct.pack_into("<I", data, CRC_OFF,
                     zlib.crc32(bytes(data[0x200:])) & 0xFFFFFFFF)
    open(args.out, "wb").write(data)

    print("section : %s  size=0x%X  flags 3->2" % (rec["name"], rec["size"]))
    print("sha256  : %s" % hashlib.sha256(new).hexdigest())
    print("crc32   : 0x%08X" % struct.unpack_from("<I", data, CRC_OFF)[0])
    if args.version is not None:
        print("version : 0x%04X" % int(args.version, 0))
    print("wrote   : %s" % args.out)


if __name__ == "__main__":
    main()

