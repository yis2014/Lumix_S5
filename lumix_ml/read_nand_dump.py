"""Read and decode the NAND stream-wrapper capture from camera RAM.

This only uses Service USB opcode 0x5c.  It does not invoke camera functions or
write memory.  The raw capture and decoded fields are saved beside the A-line
research notes so each experiment remains auditable.
"""
import json
import struct
import time

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

from usb_link import LumixServiceUSB

TARGET = 0x87F4D152
BUF = 0x87086400
COUNTER = 0x87086450
ALIAS = 0x80000000
OUTPUT = r"E:\desktop\LUMIX\analysis\nand_read_capture_latest.json"

FIELD_NOTES = [
    "destination base (loaded before final memcpy tail)",
    "destination bound/limit",
    "destination range field A",
    "destination range field B",
    "source mapping base",
    "source offset",
    "requested length",
    "status/flag bytes",
]

md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

with LumixServiceUSB() as u:
    counter = struct.unpack("<I", u.read_mem(COUNTER, 4))[0]
    buf = u.read_mem(BUF, 0x50)
    r0, r1, r2, r3, sp, lr = struct.unpack_from("<6I", buf, 0)
    fields = struct.unpack_from("<8I", buf, 0x20)

    print(f"counter = {counter}")
    print(f"r0={r0:#010x} r1={r1:#010x} r2={r2:#010x} r3={r3:#010x}")
    print(f"sp={sp:#010x} lr={lr:#010x}")
    print("stream descriptor (captured at entry, before the original prologue):")
    for i, (value, note) in enumerate(zip(fields, FIELD_NOTES)):
        print(f"  +{i * 4:#04x} = {value:#010x}  {note}")

    caller = (lr & ~1) - 4 if lr else 0
    caller_text = ""
    if 0x06000000 <= caller < 0x0A000000 or 0x86000000 <= caller < 0x8A000000:
        physical = caller if caller < 0x80000000 else caller - ALIAS
        start = physical - 0x10
        raw = u.read_mem(start + ALIAS, 0x20)
        lines = []
        print(f"caller near physical {caller:#x} (service {caller + ALIAS:#x}):")
        for ins in md.disasm(raw, start):
            prefix = ">>" if ins.address == caller else "  "
            line = f"{prefix} {ins.address:#x}: {ins.mnemonic} {ins.op_str}"
            lines.append(line)
            print(line)
        caller_text = "\n".join(lines)

record = {
    "timestamp": time.time(),
    "target_service": hex(TARGET),
    "counter": counter,
    "registers_physical": {
        "r0": hex(r0), "r1": hex(r1), "r2": hex(r2),
        "r3": hex(r3), "sp_after_hook_push": hex(sp), "lr": hex(lr),
    },
    "caller_physical": hex(caller),
    "caller_service": hex(caller + ALIAS),
    "descriptor_hex": buf[0x20:0x40].hex(),
    "descriptor_fields": [
        {"offset": hex(i * 4), "value": hex(value), "static_note": note}
        for i, (value, note) in enumerate(zip(fields, FIELD_NOTES))
    ],
    "caller_disassembly": caller_text,
    "raw_buf_0x50_hex": buf.hex(),
}
with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(record, f, ensure_ascii=False, indent=2)
print(f"saved: {OUTPUT}")
