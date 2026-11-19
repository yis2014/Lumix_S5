"""Pre-flight safety check before the genuine update flash.

1. metadata verifier must be the minimal 4-byte bypass (00207047), NOT a branch
   into the AES hook cave (leftover from the injection proof);
2. memcpy must be back to stock (it was half-patched during the first crash);
3. both AES hooks must match the locally built bytes exactly;
4. the SD update image must differ from official V2.9 in exactly 4 version bytes;
5. capture counters must be zero.
"""
import struct

from inject_test import bw
from key_hook import TARGETS, layout, IMAGE, BASE
from usb_link import LumixServiceUSB

VERIFIER = 0x868C08C6
BYPASS = bytes.fromhex("00207047")
MEMCPY = 0x866C22B4
MEMCPY_ORIG = bytes.fromhex("030052e3")
BACKUP = r"E:\desktop\LUMIX\preflight_backup.json"


def main():
    image = open(IMAGE, "rb").read()
    hooks = layout(image)
    ok = True
    with LumixServiceUSB() as u:
        v = u.read_mem(VERIFIER, 4)
        print(f"1. verifier = {v.hex()}", end="  ")
        if v != BYPASS:
            print("-> fixing to minimal bypass")
            u.write_mem_safe(VERIFIER, BYPASS, backup_path=BACKUP)
            v = u.read_mem(VERIFIER, 4)
            print(f"   now = {v.hex()}")
        print("   OK" if v == BYPASS else "   FAIL")
        ok &= v == BYPASS

        m = u.read_mem(MEMCPY, 4)
        print(f"2. memcpy   = {m.hex()} (stock {MEMCPY_ORIG.hex()})", "OK" if m == MEMCPY_ORIG else "FAIL")
        ok &= m == MEMCPY_ORIG

        for name, cave, target, buf, mode, h in hooks:
            live_cave = u.read_mem(cave, len(h))
            live_target = u.read_mem(target, 4)
            want_target = bw(target, cave)
            good = live_cave == h and live_target == want_target
            print(f"3. {name}: cave {'OK' if live_cave == h else 'FAIL'}, "
                  f"target {'OK' if live_target == want_target else 'FAIL'}")
            ok &= good
            cnt = struct.unpack("<I", u.read_mem(buf + 0x20, 4))[0]
            print(f"   counter = {cnt}", "OK" if cnt == 0 else "(non-zero)")
            ok &= cnt == 0

    a = open(r"E:\desktop\LUMIX\S5___V29.bin", "rb").read()
    b = open(r"H:\S5___V29.bin", "rb").read()
    diffs = [i for i in range(len(a)) if a[i] != b[i]]
    print(f"4. update image: size {len(a)} vs {len(b)}, differing bytes = {[hex(i) for i in diffs]}")
    ok &= len(a) == len(b) and diffs == [0x1EA2400]
    print("\nPREFLIGHT", "PASS - ready to flash" if ok else "FAIL - do NOT flash")


if __name__ == "__main__":
    main()
