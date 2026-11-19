"""LIVE READ-ONLY scan: find runtime references to the video-mode descriptors.

The descriptor pointer array itself lives inside the program image (0x865b01f0...).
Any hit OUTSIDE the image is a runtime structure (mode manager / active config),
which tells us which descriptor the camera is currently using.
"""
import json
import struct
import time

from usb_link import LumixServiceUSB

BASE = 0x86280000
DELTA = 0x80000000
IMG_END = 0x88000000
PTR_ARRAY_PHYS = 0x865B01F0
DESC_STRIDE = 0x15C

SCAN_START = 0x88000000
SCAN_END = 0x90000000
OUT = r"E:\desktop\LUMIX\stage2_active_descriptor_refs.json"


def main():
    with open(r"E:\desktop\LUMIX\program_0x86280000.bin", "rb") as f:
        blob = f.read()

    descs = {}
    a = PTR_ARRAY_PHYS
    idx = 0
    while True:
        v = struct.unpack_from("<I", blob, a - BASE)[0]
        if not (0x06000000 <= v < 0x08000000):
            break
        descs[v] = {"index": idx, "phys": v + DELTA, "virt": v}
        idx += 1
        a += 4
        if idx > 200:
            break
    print(f"{len(descs)} descriptors in pointer array, stride 0x{DESC_STRIDE:x}")
    wanted = set(descs)

    hits = []
    t0 = time.time()
    with LumixServiceUSB() as u:
        print(f"connected {u.device_path}")
        addr = SCAN_START
        while addr < SCAN_END:
            blk = u.read_block(addr)
            for off in range(0, 1024, 4):
                v = struct.unpack_from("<I", blk, off)[0]
                if v in wanted:
                    hits.append({"at": hex(addr + off), "descriptor_virt": hex(v),
                                 "descriptor_index": descs[v]["index"],
                                 "descriptor_phys": hex(descs[v]["phys"])})
            addr += 1024
            if (addr - SCAN_START) % (16 * 1024 * 1024) == 0:
                print(f"  ...0x{addr:08x}  {time.time()-t0:.0f}s  hits={len(hits)}", flush=True)

    rec = {"scan_range": [hex(SCAN_START), hex(SCAN_END)], "descriptor_count": len(descs),
           "hits": hits, "writes_performed": False, "seconds": round(time.time() - t0, 1)}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)
    print(f"\n{len(hits)} runtime references:")
    for h in hits:
        print(f"  @0x{int(h['at'],16):08x} -> descriptor#{h['descriptor_index']} phys {h['descriptor_phys']}")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
