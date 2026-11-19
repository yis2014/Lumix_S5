"""Dump a physical RAM range over Service USB (0x5c, 1 KiB blocks) for offline analysis."""
import sys
import time

from usb_link import LumixServiceUSB

START = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x80000000
END = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x86280000
OUT = sys.argv[3] if len(sys.argv) > 3 else r"E:\desktop\LUMIX\ram_low.bin"
CHUNK = 1 << 20

t0 = time.time()
with LumixServiceUSB() as u, open(OUT, "wb") as f:
    addr = START
    while addr < END:
        n = min(CHUNK, END - addr)
        for attempt in range(4):
            try:
                data = u.read_mem(addr, n)
                break
            except Exception as e:
                print(f"retry {attempt + 1} at {addr:#x}: {e}", flush=True)
                time.sleep(0.2)
        else:
            raise RuntimeError(f"read failed at {addr:#x}")
        f.write(data)
        addr += n
        print(f"{addr:#x}  {addr - START}/{END - START} bytes  {time.time() - t0:.0f}s", flush=True)
print(f"saved {OUT}")
