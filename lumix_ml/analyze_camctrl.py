"""Dissect Netmw_set_wlv_camctrl_request: tbb jump table + per-branch string refs."""
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

BIN = r"E:\desktop\LUMIX\program_0x86280000.bin"
BASE = 0x86280000
FUNC = 0x87F2CCFA
SIZE = 0x400
TBB = 0x87F2CD2A

blob = open(BIN, "rb").read()
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)


def rd(addr, n):
    return blob[addr - BASE:addr - BASE + n]


def u32(addr):
    return struct.unpack("<I", rd(addr, 4))[0]


def strat(addr):
    if not (BASE <= addr < BASE + len(blob)):
        return None
    raw = rd(addr, 96)
    end = raw.find(b"\x00")
    if end < 4:
        return None
    s = raw[:end]
    if all(32 <= b < 127 for b in s):
        return s.decode()
    return None


print("===== tbb jump table =====")
pc = (TBB + 4) & ~3
print(f"tbb @ {TBB:#x}, table base (PC) = {pc:#x}")
entries = rd(pc, 0x20)
for i, e in enumerate(entries):
    tgt = (pc + 2 * e) & 0xFFFFFFFF
    print(f"  case {i:#04x}: entry {e:#04x} -> {tgt:#x}")

print("\n===== function disassembly with resolved refs =====")
for ins in md.disasm(rd(FUNC, SIZE), FUNC):
    note = ""
    if ins.mnemonic == "adr":
        imm = int(ins.op_str.split("#")[1], 16)
        tgt = ((ins.address + 4) & ~3) + imm
        s = strat(tgt)
        note = f" ; -> {tgt:#x}" + (f' "{s}"' if s else "")
    elif ins.mnemonic.startswith("ldr") and "[pc," in ins.op_str:
        imm = int(ins.op_str.split("#")[1].rstrip("]"), 16)
        la = ((ins.address + 4) & ~3) + imm
        val = u32(la)
        s = strat(val)
        note = f" ; [{la:#x}]={val:#x}" + (f' "{s}"' if s else "")
    print(f"0x{ins.address:08x}: {ins.mnemonic:10s} {ins.op_str}{note}")
