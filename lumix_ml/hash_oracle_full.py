"""Validate the plaintext-SHA256 oracle on known partitions, then sweep RAM dumps
(page-aligned) for the small loader/postboot partitions by their directory hashes.
"""
import hashlib
import json
import os

TABLE = json.load(open(r"E:\desktop\LUMIX\firmware_table.json"))
H1 = {e["name"]: (e["size"], e["h1"]) for e in TABLE}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def check_file(path, name):
    size, want = H1[name]
    d = open(path, "rb").read(size)
    got = sha(d)
    print(f"{name}: {os.path.basename(path)} first {size} bytes -> {'MATCH' if got == want else 'no'}")
    return got == want


print("===== oracle validation on known plaintext =====")
check_file(r"E:\desktop\LUMIX\program_0x86280000.bin", "program")
check_file(r"E:\desktop\LUMIX\rootfs1_dump.bin", "rootfs1")
check_file(r"E:\desktop\LUMIX\rootfs2_dump.bin", "rootfs2")
check_file(r"E:\desktop\LUMIX\lowmem_0_2M.bin", "loader3")

print("\n===== page-aligned sweep for small partitions =====")
SMALL = ["loader1", "loader2", "postboot2", "postboot4", "postboot5",
         "zboot", "dram_sleep", "usbcharge", "ipu_code", "rc_code",
         "nr_code", "hm_c_prog", "hr_c_prog"]
DUMPS = [
    (r"E:\desktop\LUMIX\ram_low.bin", 0x80000000),
    (r"E:\desktop\LUMIX\stage2_ram_baseline.bin", 0x80000000),
]
for path, base in DUMPS:
    if not os.path.exists(path):
        continue
    d = open(path, "rb").read()
    print(f"--- {os.path.basename(path)} ({len(d)} bytes) ---")
    for name in SMALL:
        size, want = H1[name]
        hits = []
        for off in range(0, len(d) - size, 0x1000):
            if sha(d[off:off + size]) == want:
                hits.append(base + off)
        print(f"  {name:12s}: {['%#x' % h for h in hits] if hits else '-'}", flush=True)
