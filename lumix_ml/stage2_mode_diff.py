"""LIVE READ-ONLY differential across recording-mode changes.

Usage:
  python stage2_mode_diff.py baseline     # snapshot RAM while camera is in mode A
  ... change recording mode on the camera (e.g. 4K 25p -> 4K 50p) ...
  python stage2_mode_diff.py compare      # snapshot again, list every changed address

Only opcode 0x5c reads are used; nothing is written to the camera.
"""
import json
import struct
import sys
import time

from usb_link import LumixServiceUSB

SCAN_START = 0x88000000
SCAN_END = 0x90000000
SNAP = r"E:\desktop\LUMIX\stage2_ram_baseline.bin"
META = r"E:\desktop\LUMIX\stage2_ram_baseline.json"
DIFF_OUT = r"E:\desktop\LUMIX\stage2_mode_diff.json"


def snapshot(tag):
    t0 = time.time()
    buf = bytearray()
    with LumixServiceUSB() as u:
        print(f"connected {u.device_path}")
        addr = SCAN_START
        while addr < SCAN_END:
            buf += u.read_block(addr)
            addr += 1024
            if (addr - SCAN_START) % (32 * 1024 * 1024) == 0:
                print(f"  ...0x{addr:08x} {time.time()-t0:.0f}s", flush=True)
    print(f"{tag}: {len(buf)} bytes in {time.time()-t0:.0f}s")
    return bytes(buf)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    if cmd == "baseline":
        data = snapshot("baseline")
        with open(SNAP, "wb") as f:
            f.write(data)
        with open(META, "w", encoding="utf-8") as f:
            json.dump({"start": hex(SCAN_START), "end": hex(SCAN_END), "t": time.time()}, f)
        print(f"baseline saved -> {SNAP}")
        print("现在请在机身上切换录制规格（例如 4K 25p -> 4K 50p），然后运行 compare")
        return

    with open(SNAP, "rb") as f:
        old = f.read()
    new = snapshot("compare")
    if len(new) != len(old):
        raise RuntimeError("snapshot size mismatch")

    # group changed bytes into regions
    regions = []
    cur = None
    for i, (a, b) in enumerate(zip(old, new)):
        if a != b:
            if cur is None:
                cur = [i, i]
            else:
                cur[1] = i
        else:
            if cur is not None and i - cur[1] > 64:
                regions.append(cur)
                cur = None
    if cur is not None:
        regions.append(cur)

    out = []
    print(f"\n{len(regions)} changed region(s):")
    for s, e in regions:
        phys = SCAN_START + s
        length = e - s + 1
        print(f"  0x{phys:08x} .. 0x{SCAN_START+e:08x}  ({length} bytes)")
        for off in range(s, min(e + 1, s + 32), 4):
            ov = struct.unpack_from("<I", old, off)[0]
            nv = struct.unpack_from("<I", new, off)[0]
            if ov != nv:
                print(f"      +0x{off-s:04x} (0x{SCAN_START+off:08x}): {ov} -> {nv}")
        out.append({"phys": hex(phys), "length": length})

    with open(DIFF_OUT, "w", encoding="utf-8") as f:
        json.dump({"regions": out, "writes_performed": False}, f, indent=2)
    print(f"saved {DIFF_OUT}")


if __name__ == "__main__":
    main()
