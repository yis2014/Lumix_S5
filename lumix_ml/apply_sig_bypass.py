"""Apply / roll back the S5 metadata-signature bypass patch in main-core RAM.

Patch target: phys 0x868C08C6, the P-256 ECDSA metadata verifier.
Original : push {r4,r5,r6,lr} (70 b5) ; sub sp,#0xc0 (90 b0)
Patched  : movs r0,#0 (00 20)         ; bx lr        (70 47)   -> always "valid"

Verified offline with unicorn against the genuine S5 V2.9 signature:
  unpatched genuine  -> 0 (valid)      unpatched corrupted -> 1 (invalid)
  patched   corrupted-> 0 (valid)

RAM only. Nothing is written to NAND. Reboot restores stock behaviour.
"""
import sys

from usb_link import LumixServiceUSB

ADDR = 0x868C08C6
ORIG = bytes.fromhex("70b5b0b0")
PATCH = bytes.fromhex("00207047")
BACKUP = r"E:\desktop\LUMIX\sig_bypass_backup.json"


def apply():
    with LumixServiceUSB() as dev:
        current = dev.read_mem(ADDR, 4)
        print(f"current bytes @0x{ADDR:08x}: {current.hex()}")
        if current == PATCH:
            print("already patched")
            return
        if current != ORIG:
            raise SystemExit(f"unexpected prologue {current.hex()}, expected {ORIG.hex()} - aborting")
        dev.write_mem_safe(ADDR, PATCH, backup_path=BACKUP)
        verify = dev.read_mem(ADDR, 4)
        print(f"after patch  @0x{ADDR:08x}: {verify.hex()}")
        if verify != PATCH:
            raise SystemExit("readback mismatch")
        print(f"OK: metadata ECDSA verifier now always returns 0 (valid). backup={BACKUP}")
        print("RAM only; reboot or `python apply_sig_bypass.py rollback` restores stock.")


def rollback():
    with LumixServiceUSB() as dev:
        dev.rollback(BACKUP)
        print(f"restored bytes @0x{ADDR:08x}: {dev.read_mem(ADDR, 4).hex()}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        apply()
