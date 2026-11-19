"""Milestone 2 / step 1 (READ-ONLY): verify the static video table against live camera RAM.

Reads 0x86a077e4 .. +15*0x74 from the DC-S5 and diffs it against program_0x86280000.bin.
No writes are performed.
"""
import json
import struct

from usb_link import LumixServiceUSB

BIN_PATH = r"E:\desktop\LUMIX\program_0x86280000.bin"
IMG_BASE = 0x86280000
TABLE = 0x86A077E4
STRIDE = 0x74
COUNT = 15
OUT = r"E:\desktop\LUMIX\stage2_table_live_check.json"


def main():
    size = STRIDE * COUNT
    with open(BIN_PATH, "rb") as f:
        f.seek(TABLE - IMG_BASE)
        static = f.read(size)

    with LumixServiceUSB() as u:
        print(f"connected: {u.device_path}")
        live = u.read_mem(TABLE, size)

    entries = []
    diff_bytes = 0
    for i in range(COUNT):
        off = i * STRIDE
        s, l = static[off:off + STRIDE], live[off:off + STRIDE]
        d = sum(1 for a, b in zip(s, l) if a != b)
        diff_bytes += d
        br1, br2, w, h = struct.unpack_from("<IIHH", l, 4)
        entries.append({
            "index": i,
            "physical": hex(TABLE + off),
            "live_bitrate_mbps": br1 / 1e6,
            "live_bitrate2_mbps": br2 / 1e6,
            "width": w,
            "height": h,
            "diff_bytes_vs_program_bin": d,
            "identical": d == 0,
        })
        print(f"  [{i:2d}] 0x{TABLE+off:08x} {br1/1e6:7.1f} Mbps {w}x{h} diff={d}")

    rec = {
        "table_physical": hex(TABLE),
        "stride": hex(STRIDE),
        "entries": entries,
        "total_diff_bytes": diff_bytes,
        "verdict": "live RAM table identical to dumped program image" if diff_bytes == 0 else "table mutated at runtime or wrong address",
        "writes_performed": False,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)
    print(f"\ntotal diff bytes = {diff_bytes}  -> {rec['verdict']}")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
