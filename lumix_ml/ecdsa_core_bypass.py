"""Reversible RAM-only ECDSA core bypass for local S5 experiments."""
import sys
from usb_link import LumixServiceUSB

ADDR = 0x868CA60E
ORIG = bytes.fromhex('70b5bab0')
PATCH = bytes.fromhex('01207047')
BACKUP = r'E:\desktop\LUMIX\ecdsa_core_bypass_backup.json'

def main():
    rollback = len(sys.argv) > 1 and sys.argv[1] == 'rollback'
    with LumixServiceUSB() as u:
        if rollback:
            u.rollback(BACKUP)
        else:
            cur = u.read_mem(ADDR, 4)
            if cur not in (ORIG, PATCH):
                raise SystemExit(f'unexpected bytes {cur.hex()}')
            if cur == ORIG:
                u.write_mem_safe(ADDR, PATCH, backup_path=BACKUP)
        print(u.read_mem(ADDR, 4).hex())

if __name__ == '__main__':
    main()
