"""Backend for the S5 focus-sound desktop app.

Commands:
  status                         -> JSON device/table state
  dump                           -> JSON of all 28 sound-table entries
  apply <pcm-file> <samples> <region_addr> -> upload PCM and retarget ID1
  apply-id <id> <pcm> <samples> <region_addr> -> alias for apply-slot
  apply-slot <index> <pcm> <samples> <region_addr> -> guarded physical region
  restore                        -> restore the stock ID1 entry
  restore-id <id> <32-byte-hex>  -> restore any entry from a saved hex blob
  scan [start] [length]          -> read-only map of free (0x55/zero) scratch RAM

All writes are RAM-only; a battery pull restores stock behaviour.
"""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Load the Windows-only transport only when needed; pure helpers work on any OS.
S = None


def protocol():
    global S
    if S is None:
        import s5svc
        S = s5svc
    return S

TBL = 0x86E35100
ID1 = TBL + 32
SCRATCH_START = 0x8F000000
SCRATCH_END = 0x8F800000
HEADER_MAGIC = b"LMXTSLOT"
HEADER_SIZE = 16
SLOT_COUNT = 28
MAX_SAMPLES = 3 * 44100
ORIG_ID1 = bytes.fromhex(
    "010000008031aa06006aaa0680f5bf068066c00680380000b2ac310601000000"
)


def read_bytes(svc, addr, n):
    """0x5C reads need 1 KiB alignment; slice the wanted window out."""
    transport = protocol()
    aligned = addr & ~0x3FF
    skip = addr - aligned
    out = b""
    for off in range(0, skip + n, 1024):
        r = svc.exchange(transport.build_0x5c(aligned + off))
        if len(r) != 1030 or r[3] != 5:
            raise RuntimeError("read failed at 0x%X" % (aligned + off))
        out += r[4:1028]
    return out[skip:skip + n]


def validate_index(idx):
    if type(idx) is not int or not 0 <= idx < SLOT_COUNT:
        raise ValueError("index must be 0..27")
    return idx


def entry_addr(idx):
    return TBL + validate_index(idx) * 32


def validate_region(addr, samples):
    if (type(addr) is not int or addr % 1024 != 0
            or not SCRATCH_START <= addr < SCRATCH_END
            or addr + HEADER_SIZE + samples * 2 > SCRATCH_END):
        raise ValueError("region address must be 1 KiB aligned and span within 0x%08X..0x%08X"
                         % (SCRATCH_START, SCRATCH_END))
    return addr


def encode_header(idx, samples):
    validate_index(idx)
    if type(samples) is not int or not 0 < samples <= MAX_SAMPLES:
        raise ValueError("sample count out of range")
    return struct.pack("<8sII", HEADER_MAGIC, idx, samples)


def decode_header(raw):
    if len(raw) < HEADER_SIZE:
        return None
    magic, idx, samples = struct.unpack_from("<8sII", raw)
    return ((idx, samples) if magic == HEADER_MAGIC and 0 <= idx < SLOT_COUNT
            and 0 < samples <= MAX_SAMPLES else None)


def region_is_free(raw, idx):
    """The 0x8F scratch area keeps stale bytes across boots, so only an
    existing slot header for a different index counts as occupied."""
    validate_index(idx)
    header = decode_header(raw)
    if header is None:
        return True
    return header[0] == idx


class RegionNotFree(RuntimeError):
    def __init__(self, addr):
        super().__init__("region not free")
        self.address = "0x%08X" % addr


def guard_region(svc, idx, samples, addr):
    validate_region(addr, samples)
    raw = read_bytes(svc, addr, HEADER_SIZE + samples * 2)
    old_header = decode_header(raw)
    if (old_header and addr + HEADER_SIZE + old_header[1] * 2 > SCRATCH_END
            or not region_is_free(raw, idx)):
        raise RegionNotFree(addr)
    return addr


# Every address used here (sound table, body-version field, scratch RAM) was
# verified on DC-S5 firmware 2.90 only. Other firmware may keep something else
# at these addresses, so writes are refused unless the body version is listed.
VERSION_ADDR = 0x863B0000
VERIFIED_BODY_VERSIONS = {0x0290}
PROGRAM_VIRT = (0x06280000, 0x07280000)   # program image, 16 MiB at 0x86280000
LEGACY_SCRATCH_VIRT = (0x0B5B0000, 0x0BAD0000)  # scratch briefly used in commit e59b596
MAX_TABLE_BYTES = 0x100000  # +0x14 is the PCM length in bytes


class UnsupportedFirmware(RuntimeError):
    pass


def read_body_version(svc):
    return struct.unpack_from("<H", read_bytes(svc, VERSION_ADDR, 2), 0)[0]


def entry_problem(raw, idx):
    """Why a 32-byte sound-table entry does not look like entry idx (None if it does)."""
    entry_id, addr = struct.unpack_from("<II", raw, 0)
    length = struct.unpack_from("<I", raw, 0x14)[0]  # PCM bytes
    if entry_id != idx:
        return "entry %d has id %d" % (idx, entry_id)
    if not 0 < length <= MAX_TABLE_BYTES:
        return "entry %d has implausible PCM length %d bytes" % (idx, length)
    ranges = (PROGRAM_VIRT, LEGACY_SCRATCH_VIRT,
              (SCRATCH_START - 0x80000000, SCRATCH_END - 0x80000000))
    if not any(lo <= addr < hi for lo, hi in ranges):
        return "entry %d points at unexpected address 0x%08X" % (idx, addr)
    return None


def table_problem(raw):
    for i in range(SLOT_COUNT):
        problem = entry_problem(raw[i * 32:(i + 1) * 32], i)
        if problem:
            return problem
    return None


def require_writable(svc):
    """Refuse to write unless the firmware and the sound table are the verified ones."""
    ver = read_body_version(svc)
    if ver not in VERIFIED_BODY_VERSIONS:
        raise UnsupportedFirmware(
            "unsupported firmware: body version 0x%04X has not been verified "
            "(verified: %s); writing is disabled" % (
                ver, ", ".join("0x%04X" % v for v in sorted(VERIFIED_BODY_VERSIONS))))
    problem = table_problem(read_bytes(svc, TBL, SLOT_COUNT * 32))
    if problem:
        raise UnsupportedFirmware("sound table check failed: %s; writing is disabled" % problem)
    return ver


def cmd_status():
    try:
        svc = protocol().Service(settle=0.002)
    except SystemExit as exc:
        print(json.dumps({"connected": False, "error": str(exc)}))
        return
    try:
        e = read_bytes(svc, ID1, 32)
        addr = struct.unpack_from("<I", e, 4)[0]
        size = struct.unpack_from("<I", e, 0x14)[0]
        ver = read_body_version(svc)
        problem = table_problem(read_bytes(svc, TBL, SLOT_COUNT * 32))
        print(json.dumps({
            "verified": ver in VERIFIED_BODY_VERSIONS and problem is None,
            "table_problem": problem,
            "connected": True,
            "id1_addr": "0x%08X" % addr,
            "id1_bytes": size,
            "id1_samples": size // 2,
            "custom": SCRATCH_START - 0x80000000 <= addr < SCRATCH_END - 0x80000000,
            "body_version": "0x%04X" % ver,
        }))
    except Exception as exc:
        print(json.dumps({"connected": True, "error": str(exc)}))
    finally:
        svc.close()


def cmd_dump():
    svc = protocol().Service(settle=0.002)
    try:
        out = []
        for i in range(28):
            e = read_bytes(svc, entry_addr(i), 32)
            out.append({
                "index": i,
                "id": struct.unpack_from("<I", e, 0)[0],
                "addr": "0x%08X" % struct.unpack_from("<I", e, 4)[0],
                "addr2": "0x%08X" % struct.unpack_from("<I", e, 8)[0],
                "size": struct.unpack_from("<I", e, 0x14)[0],
                "bytes": struct.unpack_from("<I", e, 0x14)[0],
                "samples": struct.unpack_from("<I", e, 0x14)[0] // 2,
                "hex": e.hex(),
            })
        print(json.dumps({"ok": True, "entries": out}))
    finally:
        svc.close()


def write_halfwords(svc, addr, data):
    transport = protocol()
    for offset in range(0, len(data), 2):
        svc.exchange_write(transport.build_0x9c(addr + offset,
                                              struct.unpack_from("<H", data, offset)[0]))


def write_pcm(svc, path, samples, idx, region_addr):
    # Guard the exact header + PCM span before writing even its header.
    header = encode_header(idx, samples)
    validate_region(region_addr, samples)
    with open(path, "rb") as source:
        data = source.read()
    if len(data) != samples * 2:
        raise RuntimeError("PCM size mismatch")
    addr = guard_region(svc, idx, samples, region_addr)
    write_halfwords(svc, addr, header)
    for i in range(samples):
        write_halfwords(svc, addr + HEADER_SIZE + i * 2, data[i * 2:i * 2 + 2])
        if (i + 1) % 2000 == 0 or i + 1 == samples:
            print("PROGRESS %d %d" % (i + 1, samples), flush=True)
    return addr + HEADER_SIZE - 0x80000000


def retarget(svc, idx, samples, pcm_virt):
    base = entry_addr(idx)
    write_halfwords(svc, base + 4, struct.pack("<I", pcm_virt))
    write_halfwords(svc, base + 0x14, struct.pack("<I", samples * 2))
    return read_bytes(svc, base, 32)


def cmd_apply(path, samples, idx, region_addr):
    encode_header(idx, samples)
    validate_region(region_addr, samples)
    # File/address validation also precedes opening the device.
    if os.path.getsize(path) != samples * 2:
        raise RuntimeError("PCM size mismatch")
    svc = protocol().Service(settle=0.002)
    try:
        require_writable(svc)
        pcm_virt = write_pcm(svc, path, samples, idx, region_addr)
        e = retarget(svc, idx, samples, pcm_virt)
        ok = (struct.unpack_from("<I", e, 4)[0] == pcm_virt
              and struct.unpack_from("<I", e, 0x14)[0] == samples * 2)
        print(json.dumps({"ok": ok, "index": idx, "entry": e.hex(),
                          "error": None if ok else "table verification failed"}))
    finally:
        svc.close()


def cmd_restore():
    svc = protocol().Service(settle=0.002)
    try:
        require_writable(svc)
        for i in range(0, 32, 2):
            svc.exchange_write(protocol().build_0x9c(ID1 + i,
                                            struct.unpack_from("<H", ORIG_ID1, i)[0]))
        e = read_bytes(svc, ID1, 32)
        print(json.dumps({"ok": e == ORIG_ID1, "entry": e.hex()}))
    finally:
        svc.close()


def cmd_restore_id(idx, hexblob):
    validate_index(idx)
    raw = bytes.fromhex(hexblob)
    if len(raw) != 32:
        raise SystemExit("entry hex must be 32 bytes")
    problem = entry_problem(raw, idx)
    if problem or not PROGRAM_VIRT[0] <= struct.unpack_from("<I", raw, 4)[0] < PROGRAM_VIRT[1]:
        raise ValueError("refusing to restore: %s" % (problem or "saved entry does not point into the firmware program image"))
    svc = protocol().Service(settle=0.002)
    try:
        require_writable(svc)
        base = entry_addr(idx)
        for i in range(0, 32, 2):
            svc.exchange_write(protocol().build_0x9c(base + i,
                                            struct.unpack_from("<H", raw, i)[0]))
        e = read_bytes(svc, base, 32)
        print(json.dumps({"ok": e == raw, "index": idx, "entry": e.hex()}))
    finally:
        svc.close()


def classify_block(raw):
    """Label one 1 KiB block: 5 = 0x55 fill, 0 = zeros, H = LumixTool header, x = other data."""
    if raw == b"\x55" * len(raw):
        return "5"
    if raw == b"\x00" * len(raw):
        return "0"
    if decode_header(raw) is not None:
        return "H"
    return "x"


def summarize_blocks(start, labels, block=1024):
    """Merge consecutive block labels into [{start, end, kind, kib}] runs."""
    runs = []
    for i, kind in enumerate(labels):
        addr = start + i * block
        if runs and runs[-1]["kind"] == kind:
            runs[-1]["end"] = addr + block
        else:
            runs.append({"start": addr, "end": addr + block, "kind": kind})
    names = {"5": "free-0x55", "0": "zero", "H": "lumixtool", "x": "data"}
    return [{"start": "0x%08X" % r["start"], "end": "0x%08X" % r["end"],
             "kind": names[r["kind"]], "kib": (r["end"] - r["start"]) // 1024} for r in runs]


def cmd_scan(start=SCRATCH_START, length=SCRATCH_END - SCRATCH_START):
    """Read-only: map which 1 KiB blocks after the scratch base are free."""
    if (start % 1024 or length <= 0 or length % 1024
            or start < SCRATCH_START or start + length > SCRATCH_END):
        raise ValueError("scan range must be 1 KiB aligned within scratch RAM")
    svc = protocol().Service(settle=0.002)
    try:
        labels = []
        total = length // 1024
        for i in range(total):
            labels.append(classify_block(read_bytes(svc, start + i * 1024, 1024)))
            if (i + 1) % 256 == 0 or i + 1 == total:
                print("PROGRESS %d %d" % (i + 1, total), flush=True)
        print(json.dumps({"ok": True, "start": "0x%08X" % start, "length": length,
                          "runs": summarize_blocks(start, labels)}))
    finally:
        svc.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["status", "dump", "apply", "apply-id", "apply-slot",
                                    "restore", "restore-id", "scan"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()
    if a.cmd == "status":
        cmd_status()
    elif a.cmd == "dump":
        cmd_dump()
    elif a.cmd == "scan":
        cmd_scan(*(int(x, 0) for x in a.args[:2]))
    elif a.cmd == "apply":
        if len(a.args) != 3:
            raise ValueError("apply requires <pcm> <samples> <region_addr>")
        cmd_apply(a.args[0], int(a.args[1]), 1, int(a.args[2], 0))
    elif a.cmd in ("apply-id", "apply-slot"):
        if len(a.args) != 4:
            raise ValueError("apply-slot/apply-id requires <index> <pcm> <samples> <region_addr>")
        cmd_apply(a.args[1], int(a.args[2]), int(a.args[0]), int(a.args[3], 0))
    elif a.cmd == "restore":
        cmd_restore()
    else:
        cmd_restore_id(int(a.args[0]), a.args[1])


if __name__ == "__main__":
    try:
        main()
    except (Exception, SystemExit) as exc:
        # argparse's normal --help exit remains successful.
        if isinstance(exc, SystemExit) and exc.code in (None, 0):
            raise
        result = {"ok": False, "error": str(exc)}
        if isinstance(exc, RegionNotFree):
            result["address"] = exc.address
        print(json.dumps(result), flush=True)
