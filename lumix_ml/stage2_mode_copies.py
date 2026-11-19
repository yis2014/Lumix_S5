"""LIVE READ-ONLY: locate runtime COPIES of the video-mode sub-entries by content signature.

Each 0x74 sub-entry has  bitrate1,bitrate2,width,height  at +0x18..+0x27.
A hit outside the program image is a live config structure we could later patch.
"""
import json
import struct
import time
from collections import defaultdict

from usb_link import LumixServiceUSB

BASE = 0x86280000
DELTA = 0x80000000
PTR_ARRAY_PHYS = 0x865B01F0
SCAN_START = 0x88000000
SCAN_END = 0x90000000
OUT = r"E:\desktop\LUMIX\stage2_runtime_mode_copies.json"


def main():
    blob = open(r"E:\desktop\LUMIX\program_0x86280000.bin", "rb").read()

    descs = []
    a = PTR_ARRAY_PHYS
    while True:
        v = struct.unpack_from("<I", blob, a - BASE)[0]
        if not (0x06000000 <= v < 0x08000000):
            break
        descs.append(v + DELTA)
        a += 4

    sigs = {}          # full 16-byte signature -> label
    pair_index = defaultdict(list)   # 8-byte bitrate pair -> [signature]
    for di, dphys in enumerate(descs):
        for si, sub_off in enumerate((0x74, 0xE8)):
            s = dphys + sub_off
            b1, b2, w, h = struct.unpack_from("<IIII", blob, s - BASE + 0x18)
            if w == 0 or h == 0 or b1 == 0:
                continue
            sig = struct.pack("<IIII", b1, b2, w, h)
            label = f"desc{di}/sub{si} {w}x{h} {b1/1e6:.0f}Mbps (sub phys 0x{s:08x})"
            sigs[sig] = label
            pair_index[sig[:8]].append(sig)
    print(f"{len(descs)} descriptors, {len(sigs)} unique mode signatures, {len(pair_index)} bitrate pairs")

    hits = []
    t0 = time.time()
    with LumixServiceUSB() as u:
        print(f"connected {u.device_path}")
        addr = SCAN_START
        while addr < SCAN_END:
            blk = u.read_block(addr)
            for pair, candidates in pair_index.items():
                start = 0
                while True:
                    i = blk.find(pair, start)
                    if i < 0:
                        break
                    start = i + 4
                    for sig in candidates:
                        if blk[i:i + 16] == sig:
                            hits.append({"at": hex(addr + i), "mode": sigs[sig]})
            addr += 1024
            if (addr - SCAN_START) % (32 * 1024 * 1024) == 0:
                print(f"  ...0x{addr:08x} {time.time()-t0:.0f}s hits={len(hits)}", flush=True)

    rec = {"hits": hits, "writes_performed": False, "seconds": round(time.time() - t0, 1)}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)
    print(f"\n{len(hits)} runtime mode-structure copies:")
    for h in hits:
        print(f"  @0x{int(h['at'],16):08x}  {h['mode']}")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
