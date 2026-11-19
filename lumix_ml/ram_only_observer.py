"""Read-only RAM-only observer for a DC-S5 Service USB session.

The observer samples known code, capture, and buffer windows and writes a JSON
snapshot. It does not write RAM, execute a payload, touch Flash, or alter the
firmware update path.

Run from this directory with for example::

    python ram_only_observer.py --output ram_only_snapshot.json
"""

import argparse
import hashlib
import json
import struct
import time
from pathlib import Path

from usb_link import LumixServiceUSB


REGIONS = (
    ("reset_entry", 0x800003C4, 16),
    ("main_entry", 0x868F9A0C, 16),
    ("active_float_table", 0x87086A00, 16),
    ("capture_primary", 0x8F000100, 0x100),
    ("capture_secondary", 0x8F000200, 0x100),
)


def _record(addr, data):
    return {
        "address": f"0x{addr:08X}",
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "hex": data.hex(),
    }


def sample_once(usb):
    regions = {}
    for name, addr, size in REGIONS:
        regions[name] = _record(addr, usb.read_mem(addr, size))

    reset = bytes.fromhex(regions["reset_entry"]["hex"])
    main = bytes.fromhex(regions["main_entry"]["hex"])
    primary = bytes.fromhex(regions["capture_primary"]["hex"])
    secondary = bytes.fromhex(regions["capture_secondary"]["hex"])

    return {
        "timestamp": time.time(),
        "mode": "read-only RAM observer",
        "regions": regions,
        "interpretation": {
            "reset_entry_matches_baseline": reset[:4] == bytes.fromhex("d8f09fe5"),
            "main_entry_matches_baseline": main[:4] == bytes.fromhex("820000ea"),
            "active_float_table_prefix": regions["active_float_table"]["hex"][:16],
            "capture_primary_magic": primary[:4].hex(),
            "capture_secondary_magic": secondary[:4].hex(),
            "capture_primary_counter_u32": struct.unpack_from("<I", primary, 4)[0],
            "capture_secondary_counter_u32": struct.unpack_from("<I", secondary, 4)[0],
        },
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("ram_only_snapshot.json"))
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--interval", type=float, default=0.0)
    return parser.parse_args()


def main():
    args = parse_args()
    if args.samples < 1:
        raise SystemExit("--samples must be at least 1")
    if args.interval < 0:
        raise SystemExit("--interval cannot be negative")

    snapshots = []
    with LumixServiceUSB() as usb:
        for index in range(args.samples):
            snapshots.append(sample_once(usb))
            print(
                f"sample {index + 1}/{args.samples}: "
                f"reset={snapshots[-1]['interpretation']['reset_entry_matches_baseline']} "
                f"main={snapshots[-1]['interpretation']['main_entry_matches_baseline']} "
                f"counter={snapshots[-1]['interpretation']['capture_primary_counter_u32']}"
            )
            if index + 1 < args.samples and args.interval:
                time.sleep(args.interval)

    payload = {
        "tool": "ram_only_observer",
        "version": 1,
        "write_operations": 0,
        "snapshots": snapshots,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
