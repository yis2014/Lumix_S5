"""Scan candidate RAM regions for the update container after the camera has
started processing the SD update file. Read-only."""
import sys
sys.path.insert(0, 'tools')
import re
import s5svc as S

REGIONS = [
    (0x8C000000, 0x8D000000),
    (0x8F000000, 0x90000000),
    (0x90000000, 0x91000000),
    (0x87000000, 0x88000000),
    (0x80000000, 0x81000000),
    (0x81000000, 0x82000000),
]

PATS = [b'UPD\x00', b'loader1', b'loader2', b'rootfs1', b'postboot', b'S5___', b'MC801_allmenu']


def main():
    svc = S.Service(settle=0.001)
    try:
        for base, end in REGIONS:
            data = bytearray()
            a = base
            while a < end:
                r = svc.exchange(S.build_0x5c(a))
                data += r[4:1028]
                a += 1024
            d = bytes(data)
            found = []
            for p in PATS:
                hits = [m.start() for m in re.finditer(re.escape(p), d)]
                if hits:
                    found.append('%s x%d @%s' % (p.decode('latin-1'), len(hits),
                                                 ','.join(hex(base + h) for h in hits[:4])))
            print('0x%08X-0x%08X  %s' % (base, end, ' | '.join(found) if found else '-'))
            sys.stdout.flush()
    finally:
        svc.close()


if __name__ == '__main__':
    main()
