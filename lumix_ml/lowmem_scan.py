import sys
from usb_link import LumixServiceUSB

SBOX = bytes.fromhex("637c777bf26b6fc53001672bfed7ab76")
INV = bytes.fromhex("52096ad53036a538bf40a39e81f3d7fb")

start = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x0
end = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x2000000
out = sys.argv[3] if len(sys.argv) > 3 else r"E:\desktop\LUMIX\lowmem_dump.bin"

CH = 0x400  # 1 KiB per service read
hits = []
with LumixServiceUSB() as u, open(out, "wb") as f:
    a = start
    while a < end:
        try:
            d = u.read_mem(a, CH)
        except Exception as e:
            print(f"ERR at {a:#x}: {e}", flush=True)
            d = b"\x00" * CH
        if not d:
            d = b"\x00" * CH
        f.write(d)
        for pat, nm in ((SBOX, "SBOX"), (INV, "INV")):
            i = d.find(pat)
            while i != -1:
                print(f"{nm} at {a + i:#x}", flush=True)
                hits.append(a + i)
                i = d.find(pat, i + 1)
        a += CH
        if (a - start) % (CH * 1024) == 0:
            print(f"progress {a:#x} / {end:#x}", flush=True)
print("done, hits:", [hex(h) for h in hits], flush=True)
