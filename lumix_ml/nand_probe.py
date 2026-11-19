"""Resolve the live NAND device object and its driver function table.

Chain:
  0x87f1fdde: ldr r5,[pc,#0x3cc]  -> r5 = global state struct G (literal @0x87f201ac)
  0x87f1fdfc: str r0,[r5,#4]      -> [G+4] = NAND device handle H (from device open 0x87f4d0fe)
Then read H and dump every code-like pointer in it (read/write/ioctl candidates).
"""
import struct

from usb_link import LumixServiceUSB

BLOB = open(r"E:\desktop\LUMIX\program_0x86280000.bin", "rb").read()
BASE = 0x86280000


def off32(addr):
    return struct.unpack_from("<I", BLOB, addr - BASE)[0]


u = LumixServiceUSB()

G = off32(0x87F201AC)
print(f"global struct G = {G:#x}")
raw = u.read_mem(G, 0x40)
vals = struct.unpack("<16I", raw)
for i, v in enumerate(vals):
    print(f"  [G+{i*4:#04x}] = {v:#010x}")
H = vals[1]
print(f"NAND handle H = {H:#x}")
if 0x80000000 <= H < 0xA0000000:
    raw = u.read_mem(H, 0x100)
    for i in range(0, 0x100, 4):
        v = struct.unpack_from("<I", raw, i)[0]
        tag = ""
        if 0x86280000 <= v < 0x88000000 and (v & 1):
            tag = "  <-- code (thumb)"
        elif 0x86280000 <= v < 0x88000000:
            tag = "  <-- code?"
        if tag or i < 0x20:
            print(f"  [H+{i:#04x}] = {v:#010x}{tag}")
