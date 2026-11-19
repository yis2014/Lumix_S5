"""LIVE READ-ONLY: search the pre-image main-core RAM window for mode structures.

0x83100000 (end of Linux) .. 0x86280000 (start of main-core program image) was never
scanned before; it is a prime candidate for the RTOS heap/BSS where the active
video configuration would live.
"""
import json
import struct
import sys
import time
from collections import defaultdict

from usb_link import LumixServiceUSB

BASE = 0x86280000
DELTA = 0x80000000
PTR_ARRAY_PHYS = 0x865B01F0
SCAN_START = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x83100000
SCAN_END = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x86280000
OUT = sys.argv[3] if len(sys.argv) > 3 else r"E:\desktop\LUMIX\stage2_preimage_mode_hits.json"


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

    sigs = {}
    pair_index = defaultdict(list)
    for di, d in enumerate(descs):
        for si, sub in enumerate((0x74, 0xE8)):
            s = d + sub
            b1, b2, w, h = struct.unpack_from("<IIII", blob, s - BASE + 0x18)
            if not w or not b1:
                continue
            sig = struct.pack("<IIII", b1, b2, w, h)
            sigs[sig] = f"desc{di}/sub{si} {w}x{h} {b1/1e6:.0f}Mbps"
            pair_index[sig[:8]].append(sig)
    # also look for plain descriptor pointers (virtual or physical)
    ptr_values = {d - DELTA: f"virt-ptr desc{di}" for di, d in enumerate(descs)}
    ptr_values.update({d: f"phys-ptr desc{di}" for di, d in enumerate(descs)})

    sig_hits, ptr_hits, skipped = [], [], []
    t0 = time.time()
    with LumixServiceUSB() as u:
        print(f"connected {u.device_path}")
        addr = SCAN_START
        while addr < SCAN_END:
            try:
                blk = u.read_block(addr)
            except RuntimeError as e:
                skipped.append(hex(addr))
                print(f"  [skip] 0x{addr:08x}: {e}", flush=True)
                addr += 1024
                continue
            for pair, cands in pair_index.items():
                start = 0
                while True:
                    i = blk.find(pair, start)
                    if i < 0:
                        break
                    start = i + 4
                    for sig in cands:
                        if blk[i:i + 16] == sig:
                            sig_hits.append({"at": hex(addr + i), "mode": sigs[sig]})
            for off in range(0, 1024, 4):
                v = struct.unpack_from("<I", blk, off)[0]
                if v in ptr_values:
                    ptr_hits.append({"at": hex(addr + off), "kind": ptr_values[v]})
            addr += 1024
            if (addr - SCAN_START) % (8 * 1024 * 1024) == 0:
                print(f"  ...0x{addr:08x} {time.time()-t0:.0f}s sig={len(sig_hits)} ptr={len(ptr_hits)}", flush=True)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"signature_hits": sig_hits, "pointer_hits": ptr_hits, "skipped_blocks": skipped,
                   "range": [hex(SCAN_START), hex(SCAN_END)], "writes_performed": False}, f, indent=2)
    print(f"\nsignature hits: {len(sig_hits)}")
    for h in sig_hits:
        print(f"  @0x{int(h['at'],16):08x} {h['mode']}")
    print(f"pointer hits: {len(ptr_hits)}")
    for h in ptr_hits[:40]:
        print(f"  @0x{int(h['at'],16):08x} {h['kind']}")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
