"""Scan DC-S5 high DRAM (read-only 0x5c) to locate active OSD / Display / LiveView VRAM planes."""
import math
import sys
import time
from collections import Counter

from usb_link import LumixServiceUSB


def shannon_entropy(b: bytes) -> float:
    if not b:
        return 0.0
    counts = Counter(b)
    n = len(b)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def is_dram_poweron_noise(b: bytes) -> bool:
    """Uninitialized DRAM cells on PVC03V show characteristic {0x55,0xD5,0x75,0x54,0xAA,0xEA,0xAE} bias."""
    s1 = sum(1 for x in b if x in (0x55, 0xD5, 0x75, 0x54, 0x51, 0x5D, 0x45, 0xdd))
    s2 = sum(1 for x in b if x in (0xAA, 0xEA, 0xAE, 0xAB, 0xBA, 0xFA, 0xEE, 0x8A))
    return s1 > 320 or s2 > 320


def main():
    t0 = time.time()
    candidates = []
    with LumixServiceUSB() as usb:
        print(f"Connected to {usb.device_path}")
        print("Scanning 0x88000000 .. 0xA0000000 in 1 MiB steps (384 blocks, ~0.5s)...")
        p1 = {}
        for addr in range(0x88000000, 0xA0000000, 0x00100000):
            b = usb.read_block(addr)
            nz = sum(1 for x in b if x not in (0x00, 0xFF))
            if nz == 0 or is_dram_poweron_noise(b):
                continue
            ent = shannon_entropy(b)
            p1[addr] = (b, nz, ent)

        time.sleep(0.5)
        print(f"Found {len(p1)} non-empty, non-noise 1 MiB regions. Checking live activity...")
        for addr, (b1, nz, ent) in sorted(p1.items()):
            b2 = usb.read_block(addr)
            diff = sum(1 for x, y in zip(b1, b2) if x != y)
            # Check pixel-like periodicity (4-byte RGBA or 2-byte YUYV correlation)
            corr4 = sum(1 for i in range(0, 1020, 4) if b1[i+3] == b1[i+7]) / 255.0
            corr2 = sum(1 for i in range(0, 1020, 2) if abs(b1[i] - b1[i+2]) <= 4) / 510.0
            tag = "LIVE-DMA" if diff > 0 else "STATIC"
            print(
                f"  0x{addr:08x} [{tag:8s} diff={diff:4d}] nz={nz:4d} ent={ent:4.2f} "
                f"a4={corr4:.2f} y2={corr2:.2f} | {b2[:24].hex(' ')}"
            )
            candidates.append((addr, tag, diff, ent, corr4, corr2))
    print(f"Scan finished in {time.time()-t0:.2f}s")


if __name__ == "__main__":
    main()
