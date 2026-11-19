"""Locate the metadata ECDSA verifier by following references to the public key."""
import struct

from thumb_calls import disasm

BIN = r"E:\desktop\LUMIX\program_0x86280000.bin"
BASE = 0x86280000
DELTA = 0x80000000
blob = open(BIN, "rb").read()


def refs(lo, hi):
    out = []
    for off in range(0, len(blob) - 4, 4):
        v = struct.unpack_from("<I", blob, off)[0]
        if lo <= v <= hi:
            out.append((BASE + off, v))
    return out


def main():
    zones = {
        "pubkey": (0x06F53700, 0x06F53770),
        "p256_params": (0x06F0D8C0, 0x06F0D920),
    }
    for name, (lo, hi) in zones.items():
        hits = refs(lo, hi)
        print(f"\n===== {name}: {len(hits)} refs =====")
        for addr, val in hits[:8]:
            print(f"  @ phys 0x{addr:08x} -> virt 0x{val:08x}")
            print(disasm(blob, addr - 0x60, 0x60))


if __name__ == "__main__":
    main()
