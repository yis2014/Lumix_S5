"""Read the physical-address dump payload results and resolve vtables.

BUF layout (all runtime values are PHYSICAL addresses; +0x80000000 = service alias):
  BUF+0x00 : r0,r1,r2,r3,sp,lr
  BUF+0x20 : r0 object[0..3]  (obj[0] = candidate vtable pointer)
  BUF+0x30 : r1 object[0..3]
"""
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

from usb_link import LumixServiceUSB

COUNTER = 0x87086450
BUF = 0x87086400
ALIAS = 0x80000000

u = LumixServiceUSB()
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)


def rd_phys(addr, n):
    return u.read_mem(addr + ALIAS, n)


cnt = struct.unpack("<I", u.read_mem(COUNTER, 4))[0]
buf = u.read_mem(BUF, 0x50)
r0, r1, r2, r3, sp, lr = struct.unpack_from("<6I", buf, 0)
print(f"counter = {cnt}")
print(f"r0={r0:#010x} r1={r1:#010x} r2={r2:#010x} r3={r3:#010x} sp={sp:#010x} lr={lr:#010x}")


def is_code(p):
    return 0x06000000 <= p < 0x0A000000 or 0x86000000 <= p < 0x8A000000


def dump_vtable(vt):
    if not is_code(vt):
        print(f"  obj[0]={vt:#x} not a code pointer")
        return
    raw = rd_phys(vt & ~1, 0x40)
    print(f"  vtable @ {vt:#x}:")
    for i in range(0, 0x40, 4):
        fn = struct.unpack_from("<I", raw, i)[0]
        note = ""
        if is_code(fn) and (fn & 1):
            try:
                ins = list(md.disasm(rd_phys(fn & ~1, 6), fn & ~1, count=2))
                note = "  ; " + " ; ".join(f"{x.mnemonic} {x.op_str}" for x in ins)
            except Exception:
                pass
        print(f"    [{i//4:2d}] {fn:#010x}{note}")


for tag, off in (("r0", 0x20), ("r1", 0x30), ("r2", 0x40)):
    vals = struct.unpack_from("<4I", buf, off)
    print(f"\n{tag} object dwords: {[hex(v) for v in vals]}")
    dump_vtable(vals[0])

if is_code(lr):
    site = (lr & ~1) - 4
    print(f"\ncaller near {site:#x}:")
    for ins in md.disasm(rd_phys(site - 0x10, 0x20), site - 0x10):
        print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
