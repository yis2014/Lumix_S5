"""Read the captured FW-update worker globals; Service USB read-only."""
import json
import struct
import time

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from usb_link import LumixServiceUSB

BUF = 0x87086400
COUNTER = 0x870864F0
ALIAS = 0x80000000
OUTPUT = r"E:\desktop\LUMIX\analysis\fwupdate_entry_capture_latest.json"
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

with LumixServiceUSB() as u:
    counter = struct.unpack("<I", u.read_mem(COUNTER, 4))[0]
    buf = u.read_mem(BUF, 0x100)
    regs = struct.unpack_from("<6I", buf, 0)
    g_ptr, s_ptr = struct.unpack_from("<II", buf, 0x40)
    g_raw = buf[0x60:0xA0]
    s_raw = buf[0xA0:0xE0]

    print(f"counter = {counter}")
    print("saved r0-r3/sp/lr:", [hex(x) for x in regs])
    print(f"G = {g_ptr:#010x}; S = {s_ptr:#010x}")
    for name, raw in (("G", g_raw), ("S", s_raw)):
        print(f"{name} captured dwords:")
        for off in range(0, 0x40, 4):
            value = struct.unpack_from("<I", raw, off)[0]
            print(f"  +{off:#04x} = {value:#010x}")

    lr = regs[5]
    caller = (lr & ~1) - 4 if lr else 0
    caller_lines = []
    if 0x06000000 <= caller < 0x0E000000 or 0x86000000 <= caller < 0x8E000000:
        physical = caller if caller < 0x80000000 else caller - ALIAS
        start = physical - 8
        raw = u.read_mem(start + ALIAS, 0x10)
        print(f"caller near physical {caller:#x} (service {caller + ALIAS:#x}):")
        for ins in md.disasm(raw, start):
            prefix = ">>" if ins.address == caller else "  "
            line = f"{prefix} {ins.address:#x}: {ins.mnemonic} {ins.op_str}"
            caller_lines.append(line)
            print(line)

record = {
    "timestamp": time.time(),
    "counter": counter,
    "registers": [hex(x) for x in regs],
    "G": hex(g_ptr),
    "S": hex(s_ptr),
    "G_dwords": [hex(x) for x in struct.unpack("<16I", g_raw)],
    "S_dwords": [hex(x) for x in struct.unpack("<16I", s_raw)],
    "G_hex": g_raw.hex(),
    "S_hex": s_raw.hex(),
    "caller_physical": hex(caller),
    "caller_service": hex(caller + ALIAS),
    "caller_disassembly": "\n".join(caller_lines),
    "raw_buf_hex": buf.hex(),
}
with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(record, f, ensure_ascii=False, indent=2)
print(f"saved: {OUTPUT}")
