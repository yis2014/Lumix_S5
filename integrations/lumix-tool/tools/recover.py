"""One-command recovery helper for the S5 service mode.

Reads the camera state, and with --apply sets the RAM version fields to a low
value (2.00) and enables the update signature bypass, so an official package
(lower than the installed version) is accepted again.

Usage:
  python tools/recover.py            # read-only status
  python tools/recover.py --apply    # write version=2.00 and bypass=1
  python tools/recover.py --version 0x0200 --apply
"""
import argparse
import sys

sys.path.insert(0, "tools")
import s5svc as S

VER_FIELDS = [0x863B0000, 0x863B0002, 0x863181E2, 0x863181E4]
BYPASS = 0x8631801A


def read16(svc, addr):
    r = svc.exchange(S.build_0x9b(addr))
    return int.from_bytes(r[4:6], "little")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--version", type=lambda s: int(s, 0), default=0x0200)
    a = ap.parse_args()

    svc = S.Service(settle=0.002)
    try:
        print("current state:")
        for addr in VER_FIELDS:
            print("  0x%08X = 0x%04X" % (addr, read16(svc, addr)))
        print("  0x%08X = 0x%04X (bypass: 0=verify, 1=skip)" % (BYPASS, read16(svc, BYPASS)))

        if not a.apply:
            print("\nread-only. use --apply to set version=0x%04X and bypass=1"
                  % a.version)
            return

        for addr in VER_FIELDS:
            S.cmd_write16(svc, addr, a.version)
        S.cmd_write16(svc, BYPASS, 1)
        print("\nafter apply:")
        for addr in VER_FIELDS:
            print("  0x%08X = 0x%04X" % (addr, read16(svc, addr)))
        print("  0x%08X = 0x%04X" % (BYPASS, read16(svc, BYPASS)))
        print("\nnext: warm reboot (power switch, keep battery), then run the")
        print("official firmware update from the SD card.")
    finally:
        svc.close()


if __name__ == "__main__":
    main()
