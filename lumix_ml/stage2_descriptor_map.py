"""Offline: decode all 28 video-mode descriptors into a structured JSON map.

Layout (verified against program_0x86280000.bin):
  pointer array @ phys 0x865b01f0, entries are VIRTUAL pointers (phys - 0x80000000)
  descriptor size 0x15c, contains two 0x74 sub-entries at +0x74 and +0xe8
  sub-entry: +0x18 bitrate1, +0x1c bitrate2, +0x20 width, +0x24 height,
             +0x28 codec, +0x34 fps, +0x48 link clock, +0x4c fps fraction (1001)
"""
import json
import struct

BASE = 0x86280000
DELTA = 0x80000000
PTR_ARRAY_PHYS = 0x865B01F0
OUT = r"E:\desktop\LUMIX\stage2_descriptor_map.json"


def main():
    blob = open(r"E:\desktop\LUMIX\program_0x86280000.bin", "rb").read()
    descs = []
    a = PTR_ARRAY_PHYS
    while True:
        v = struct.unpack_from("<I", blob, a - BASE)[0]
        if not (0x06000000 <= v < 0x08000000):
            break
        descs.append((len(descs), a, v + DELTA))
        a += 4

    out = []
    for di, pa, dphys in descs:
        d = {"index": di, "pointer_slot_phys": hex(pa), "descriptor_phys": hex(dphys),
             "descriptor_virt": hex(dphys - DELTA), "sub_entries": []}
        for si, sub_off in enumerate((0x74, 0xE8)):
            s = dphys + sub_off
            o = s - BASE
            b1, b2, w, h, codec = struct.unpack_from("<IIIII", blob, o + 0x18)
            fps = struct.unpack_from("<I", blob, o + 0x34)[0]
            clk = struct.unpack_from("<I", blob, o + 0x48)[0]
            frac = struct.unpack_from("<I", blob, o + 0x4C)[0]
            mem_a, _, mem_b, mem_c = struct.unpack_from("<IIII", blob, o)
            d["sub_entries"].append({
                "sub": si, "sub_phys": hex(s),
                "bitrate1_field_phys": hex(s + 0x18), "bitrate2_field_phys": hex(s + 0x1C),
                "bitrate1_mbps": b1 / 1e6, "bitrate2_mbps": b2 / 1e6,
                "width": w, "height": h, "codec": codec, "fps_field": fps,
                "link_clock": clk, "fps_fraction": frac,
                "mem_sizes": [mem_a, mem_b, mem_c],
            })
        out.append(d)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"descriptor_stride": "0x15c", "sub_offsets": ["0x74", "0xe8"],
                   "descriptors": out}, f, indent=2)

    for d in out:
        for s in d["sub_entries"]:
            print(f"desc{d['index']:2d}/sub{s['sub']} phys {s['sub_phys']} "
                  f"{s['width']:5d}x{s['height']:<5d} codec={s['codec']:2d} fps~{s['fps_field']:3d} "
                  f"br={s['bitrate1_mbps']:6.1f}/{s['bitrate2_mbps']:6.1f} Mbps")
    print(f"\nsaved {OUT}")


if __name__ == "__main__":
    main()
