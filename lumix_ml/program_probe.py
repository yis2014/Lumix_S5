"""Read-only static probe for the dumped DC-S5 main-core program image.

This tool extracts evidence and candidates only. It does not generate a patch and
never communicates with the camera. Runtime addresses must be validated by
read-only differential captures before any RAM modification is considered.
"""
import argparse
import json
import struct

PHYS_BASE = 0x86280000
VIRT_BASE = 0x06280000
BITRATE_LOGGER = 0x8775C210
VIDEO_TABLE = 0x86A077E4
VIDEO_STRIDE = 0x74


def u32(data, phys):
    return struct.unpack_from("<I", data, phys - PHYS_BASE)[0]


def parse_video_table(data):
    entries = []
    for index in range(200):
        address = VIDEO_TABLE + index * VIDEO_STRIDE
        words = struct.unpack_from("<30I", data, address - PHYS_BASE)
        bitrate = words[1]
        width, height, fps_field = words[3], words[4], words[8]
        valid = (
            bitrate == words[2]
            and 1_000_000 <= bitrate <= 1_000_000_000
            and bitrate % 1_000_000 == 0
            and 320 <= width <= 8192
            and 240 <= height <= 8192
            and 1 <= fps_field <= 240
        )
        if not valid:
            break
        entries.append(
            {
                "index": index,
                "entry_physical": f"0x{address:08x}",
                "bitrate_field_physical": f"0x{address + 4:08x}",
                "bitrate_bps": bitrate,
                "bitrate_mbps": bitrate // 1_000_000,
                "width": width,
                "height": height,
                "fps_field_unverified": fps_field,
                "codec_field_unverified": words[5],
                "plausible_s5_mode": width <= 5184 and height <= 3744,
            }
        )
    return entries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("program", help="program_0x86280000.bin")
    parser.add_argument("output", help="JSON evidence output")
    args = parser.parse_args()
    with open(args.program, "rb") as f:
        data = f.read()
    if len(data) != 0x1D80000:
        raise ValueError(f"unexpected program size: {len(data):#x}")

    entries = parse_video_table(data)
    result = {
        "image": {
            "physical_base": f"0x{PHYS_BASE:08x}",
            "main_core_virtual_base": f"0x{VIRT_BASE:08x}",
            "size": len(data),
        },
        "bitrate_logger": {
            "function_physical": f"0x{BITRATE_LOGGER:08x}",
            "format_string_physical": "0x8775c609",
            "format": "TSTargetBitrate = %d, TSMaxBitrate = %d, TSMinBitrate = %d",
            "object_offsets": {
                "trans_bitrate_wats": "0x20",
                "trans_bitrate": "0x24",
                "ts_target_bitrate": "0x28",
                "ts_max_bitrate": "0x2c",
                "ts_min_bitrate": "0x30",
                "width_candidate": "0x34",
                "height_candidate": "0x38",
                "input_frame_rate_u16_candidate": "0x40",
                "frame_rate_u16_candidate": "0x42",
            },
            "status": "instruction-level layout candidate; not a global runtime address",
        },
        "video_table": {
            "first_entry_physical": f"0x{VIDEO_TABLE:08x}",
            "stride": f"0x{VIDEO_STRIDE:x}",
            "bitrate_offset_in_entry": "0x04",
            "second_bitrate_offset_in_entry": "0x08",
            "width_offset_in_entry": "0x0c",
            "height_offset_in_entry": "0x10",
            "entry_count_in_contiguous_block": len(entries),
            "entries": entries,
            "status": "static table candidate; runtime selection and mutability unverified",
        },
        "safety": {
            "camera_writes_performed": False,
            "nand_writes_performed": False,
            "next_step": "read-only live differential across two recording modes; do not patch static candidates directly",
        },
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"Wrote {args.output}: {len(entries)} video-table candidates")
    for entry in entries:
        print(
            f"  {entry['bitrate_field_physical']}  {entry['bitrate_mbps']:>3} Mbps  "
            f"{entry['width']}x{entry['height']}  S5-candidate={entry['plausible_s5_mode']}"
        )


if __name__ == "__main__":
    main()
