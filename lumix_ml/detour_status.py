"""Read-only status check of the lens-verifier detour (no writes)."""
import struct

from usb_link import LumixServiceUSB

VERIFIER = 0x868C08C6   # lens verify wrapper (Thumb), detoured
CAVE = 0x87086200       # hook code cave in rodata
COUNTER = 0x87086240    # invocation counter
ORIG_VERIFIER = bytes.fromhex("3ff69bb3")
DETOUR_VERIFIER = bytes.fromhex("c5f39bb4")


def main():
    with LumixServiceUSB() as u:
        print(f"device: {u.device_path}")
        v = u.read_mem(VERIFIER, 4)
        state = ("DETOUR" if v == DETOUR_VERIFIER else
                 "STOCK" if v == ORIG_VERIFIER else "UNKNOWN")
        print(f"verifier 0x{VERIFIER:08X} = {v.hex()}  -> {state}")

        cave = u.read_mem(CAVE, 48)
        print(f"cave     0x{CAVE:08X} = {cave.hex()}")

        cnt = struct.unpack("<I", u.read_mem(COUNTER, 4))[0]
        print(f"counter  0x{COUNTER:08X} = {cnt}")


if __name__ == "__main__":
    main()
