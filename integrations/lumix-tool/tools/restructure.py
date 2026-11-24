"""Restructure the archive into RAW / OBSERVATIONS / DERIVED / ANALYSIS / TOOLS.

RAW        untouched bytes as acquired
DERIVED    computed from RAW (merged dumps, carved images, decoded/verified copies)
ANALYSIS   written observations and interpretation
OBSERVATIONS  operator/AI transcriptions of device behaviour
"""
import hashlib
import os
import shutil
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")
ARC = os.path.join(ROOT, "archive")

MOVES = [
    # (source under out/, destination relative to archive/, category)
    ("S5___V29.bin", "RAW/firmware/S5___V29.bin", "RAW"),
    ("ram_80000000.bin", "RAW/ram/0x80000000_0x80C00000_lo.bin", "RAW"),
    ("ram_hi.bin", "RAW/ram/0x80C00000_0x81120000_hi.bin", "RAW"),
    ("ram_tail.bin", "RAW/ram/0x81120000_0x81140000_tail.bin", "RAW"),
    ("ram_beyond.bin", "RAW/ram/0x81140000_0x83000000_beyond.bin", "RAW"),
    ("probe_4000A800.bin", "RAW/probes/0x4000A800_1k.bin", "RAW"),
    ("loader3_plain.bin", "DERIVED/loader3_plain.bin", "DERIVED"),
    ("loader3_disasm.txt", "DERIVED/loader3_disasm.txt", "DERIVED"),
    ("rootfs.squashfs", "DERIVED/rootfs_0x807D3000.squashfs", "DERIVED"),
    ("ram_full.bin", "DERIVED/ram_0x80000000_0x81140000.bin", "DERIVED"),
]

TOOLS = ["s5svc.py", "s5key.py", "lumixupd.py", "parse.py", "mkarchive.py"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def section_map(fw_path, out_path):
    b = open(fw_path, "rb").read()
    rows = []
    off = 0x2EC
    while off + 0x5C <= len(b):
        name = b[off:off + 12].split(b"\0")[0]
        if not name or not all(32 <= c < 127 for c in name):
            break
        img, size, flash, flags = struct.unpack_from("<4I", b, off + 12)
        digest = b[off + 0x1C:off + 0x3C].hex()
        iv = b[off + 0x3C:off + 0x4C].hex()
        rows.append((name.decode(), img, size, flash, flags, digest, iv))
        off += 0x5C
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# S5 v2.9 section map (48 records, parsed from the official container)\n")
        f.write("# name         img_off   size      flash_addr flags sha256(plaintext)                                                 iv\n")
        for n, img, size, flash, flags, d, iv in rows:
            f.write("%-12s 0x%08X 0x%08X 0x%08X %5d %s %s\n" % (n, img, size, flash, flags, d, iv))
        f.write("\n# sum(size)=0x%X  data_start=0x%X  file_size=0x%X\n"
                % (sum(r[2] for r in rows), 0x200 + min(r[1] for r in rows), len(b)))


def main():
    for d in ("RAW/firmware", "RAW/ram", "RAW/probes", "DERIVED", "TOOLS",
              "ANALYSIS", "OBSERVATIONS"):
        os.makedirs(os.path.join(ARC, d), exist_ok=True)

    # move artifacts into place
    for src, dst, _ in MOVES:
        sp = os.path.join(OUT, src)
        dp = os.path.join(ARC, dst)
        if os.path.exists(sp) and not os.path.exists(dp):
            shutil.copy2(sp, dp)
            print("copied", src, "->", dst)
    for t in TOOLS:
        sp = os.path.join(ROOT, "tools", t)
        dp = os.path.join(ARC, "TOOLS", t)
        if os.path.exists(sp) and not os.path.exists(dp):
            shutil.copy2(sp, dp)

    # merged 48 MiB RAM image (derived)
    merged = os.path.join(ARC, "DERIVED", "ram_0x80000000_0x83000000.bin")
    if not os.path.exists(merged):
        with open(merged, "wb") as f:
            for name in ("ram_80000000.bin", "ram_hi.bin", "ram_tail.bin", "ram_beyond.bin"):
                p = os.path.join(OUT, name)
                if os.path.exists(p):
                    with open(p, "rb") as s:
                        shutil.copyfileobj(s, f)
        print("merged RAM ->", merged, os.path.getsize(merged))

    section_map(os.path.join(ARC, "RAW/firmware/S5___V29.bin"),
                os.path.join(ARC, "DERIVED", "section-map.txt"))

    # manifest
    lines = []
    for base, dirs, files in os.walk(ARC):
        dirs.sort()
        for fn in sorted(files):
            if fn == "MANIFEST.txt":
                continue
            p = os.path.join(base, fn)
            rel = os.path.relpath(p, ARC).replace("\\", "/")
            cat = rel.split("/")[0]
            lines.append((rel, cat, os.path.getsize(p), sha256(p)))
    with open(os.path.join(ARC, "MANIFEST.txt"), "w", encoding="utf-8") as f:
        f.write("# category  size  sha256  path\n")
        for rel, cat, size, h in lines:
            f.write("%-12s %10d  %s  %s\n" % (cat, size, h, rel))
    print("manifest:", len(lines), "files")


if __name__ == "__main__":
    main()
