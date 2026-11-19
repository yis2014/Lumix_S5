"""Minimal arbitrary physical-memory read via Service USB 0x5c (1KiB units).
Usage: python fast_read.py <hex_addr> <hex_size> <out.bin>
"""
import sys

from usb_link import LumixServiceUSB

addr = int(sys.argv[1], 0)
size = int(sys.argv[2], 0)
out = sys.argv[3]

u = LumixServiceUSB()
data = bytearray()
for off in range(0, size, 0x400):
    n = min(0x400, size - off)
    r = u.read_mem(addr + off, n)
    if r is None or len(r) < n:
        print(f"FAIL at {addr + off:#x}", flush=True)
        break
    data += r[:n]
    if off % 0x10000 == 0:
        print(f"{addr + off:#x} ok", flush=True)
open(out, "wb").write(bytes(data))
print(f"saved {len(data)} bytes -> {out}")
