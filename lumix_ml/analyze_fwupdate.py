"""Disassemble the FW_UPDATE_MODE handler and each tbb case target with refs."""
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

BIN = r"E:\desktop\LUMIX\program_0x86280000.bin"
BASE = 0x86280000
blob = open(BIN, "rb").read()
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

RANGES = [
    ("prev fn tail (FW_UPDATE_MODE logger)", 0x87F2CB80, 0x17A),
    ("case 0x12", 0x87F2CE00, 0x80),
    ("case 0x0e", 0x87F2CE7C, 0x54),
    ("case 0x15", 0x87F2CED0, 0x1A),
    ("case 0x16", 0x87F2CEEA, 0x12),
    ("case 0x17", 0x87F2CEFC, 0x10),
    ("case 0x00/0x12 tbl", 0x87F2CD3C, 0x10),
    ("case 0x02", 0x87F2CD4C, 0x08),
    ("case 0x10", 0x87F2CD54, 0x28),
    ("case 0x13", 0x87F2CD7C, 0x2C),
    ("case 0x1b", 0x87F2CDA8, 0x18),
    ("default", 0x87F2CDC0, 0x40),
]


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


def bl_target(ins):
    if ins.mnemonic not in ("bl", "blx"):
        return None
    try:
        return int(ins.op_str.replace("#", ""), 16)
    except ValueError:
        return None


for title, start, size in RANGES:
    print(f"\n===== {title} @ {start:#x} =====")
    for ins in md.disasm(rd(start, size), start):
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
        elif ins.mnemonic == "bl":
            t = bl_target(ins)
            if t:
                note = f" ; fn {t:#x}"
        print(f"0x{ins.address:08x}: {ins.mnemonic:10s} {ins.op_str}{note}")
