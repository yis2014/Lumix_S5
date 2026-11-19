import sys

import numpy as np

from usb_link import LumixServiceUSB

# Coarse scan of the whole low 2 GB for memory-mapped flash / non-DRAM content.
# We look for a second copy of the main-core program image (which is plaintext in flash).
PROG_SIG = open(r"E:\desktop\LUMIX\program_0x86280000.bin", "rb").read(0x400)

start = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x0
end = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x80000000
step = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x100000

interesting = []
with LumixServiceUSB() as u:
    a = start
    while a < end:
        try:
            d = u.read_block(a)
        except Exception as e:
            print(f"{a:#010x} ERR {str(e)[:40]}", flush=True)
            a += step
            continue
        arr = np.frombuffer(d, dtype=np.uint8)
        zeros = float((arr == 0).mean())
        fill55 = float((arr == 0x55).mean())
        fillaa = float((arr == 0xAA).mean())
        uniq = len(np.unique(arr))
        tag = ""
        if d[:16] == PROG_SIG[:16]:
            tag = "  <== PROGRAM IMAGE MATCH"
        if zeros > 0.999 or fill55 > 0.999 or fillaa > 0.999:
            kind = "empty"
        else:
            kind = "DATA"
            interesting.append(a)
        if kind == "DATA" or tag:
            print(f"{a:#010x} {kind} zeros={zeros:.2f} 55={fill55:.2f} aa={fillaa:.2f} uniq={uniq} head={d[:16].hex()}{tag}", flush=True)
        a += step
        if ((a - start) // step) % 64 == 0:
            print(f"...progress {a:#010x} / {end:#010x}, DATA so far={len(interesting)}", flush=True)
print("DATA regions:", [hex(x) for x in interesting], flush=True)
