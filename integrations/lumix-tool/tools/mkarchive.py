"""Build the analysis archive: merge RAM dumps, copy artifacts, hash, write README.

Everything here is read-only data already acquired from the owner's own camera
or downloaded from Panasonic's public firmware download page.
"""
import hashlib
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")
ARC = os.path.join(ROOT, "archive")

FILES = [
    # (source, archive name, description)
    ("S5___V29.bin", "S5___V29.bin", "official Panasonic S5 v2.9 update container (90,238,464 bytes)"),
    ("ram_80000000.bin", "ram_80000000_lo.bin", "RAM 0x80000000..0x80C00000 (12 MiB)"),
    ("ram_hi.bin", "ram_80000000_hi.bin", "RAM 0x80C00000..0x81120000 (5.25 MiB)"),
    ("loader3_plain.bin", "loader3_plain.bin", "decrypted loader3 (49,152 bytes, SHA-256 verified)"),
    ("loader3_disasm.txt", "loader3_disasm.txt", "ARM32 disassembly of loader3 (capstone.js)"),
    ("probe_4000A800.bin", "probe_4000A800.bin", "1 KiB probe of 0x4000A800 (all zero)"),
    ("ram_tail.bin", "ram_tail.bin", "RAM 0x81120000..0x81140000 (128 KiB, covers squashfs tail)"),
    ("rootfs.squashfs", "rootfs.squashfs", "squashfs image carved from RAM at 0x807D3000 (9,826,740 B); superblock valid, body not LZO-decompressible"),
    ("ram_full.bin", "ram_full_0x80000000_0x81140000.bin", "full contiguous RAM dump 0x80000000..0x81140000"),
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    os.makedirs(ARC, exist_ok=True)

    # merge the two contiguous RAM windows into one file
    merged = os.path.join(ARC, "ram_80000000_0x81120000.bin")
    if not os.path.exists(merged):
        with open(merged, "wb") as f:
            for name in ("ram_80000000.bin", "ram_hi.bin"):
                p = os.path.join(OUT, name)
                if os.path.exists(p):
                    with open(p, "rb") as s:
                        shutil.copyfileobj(s, f)
        print("merged ->", merged, os.path.getsize(merged))

    lines = []
    for src, dst, desc in FILES:
        sp = os.path.join(OUT, src)
        if not os.path.exists(sp):
            lines.append((dst, "MISSING", 0, desc))
            continue
        dp = os.path.join(ARC, dst)
        if not os.path.exists(dp):
            shutil.copy2(sp, dp)
        lines.append((dst, sha256(dp), os.path.getsize(dp), desc))

    if os.path.exists(merged):
        lines.append((os.path.basename(merged), sha256(merged), os.path.getsize(merged),
                      "contiguous RAM 0x80000000..0x81120000"))

    for name in ("s5svc.py", "s5key.py", "lumixupd.py", "parse.py"):
        sp = os.path.join(ROOT, "tools", name)
        if os.path.exists(sp):
            dp = os.path.join(ARC, "tools_" + name)
            if not os.path.exists(dp):
                shutil.copy2(sp, dp)
            lines.append(("tools_" + name, sha256(dp), os.path.getsize(dp), "tool source"))

    with open(os.path.join(ARC, "MANIFEST.txt"), "w", encoding="utf-8") as f:
        for name, h, size, desc in lines:
            f.write("%-40s %s %10d  %s\n" % (name, h, size, desc))
    print("manifest written")


if __name__ == "__main__":
    main()
