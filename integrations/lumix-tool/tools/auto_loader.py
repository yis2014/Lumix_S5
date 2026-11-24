"""Watch for the S5 in service mode and load a program automatically.

Every time the camera shows up as 04DA:2370 (service mode), this script writes
the program to RAM and patches the hook. Use --restore to undo the hook and
clear the program area.

Usage:
  python tools/auto_loader.py --file X:\\LUMIX\\prog.bin [--once] [--restore]
  python tools/auto_loader.py --file prog.bin --once      # single shot
"""
import argparse, json, sys, time

sys.path.insert(0, 'tools')
import s5svc as S

HOOK = 0x8647994C
HOOK_ORIG = bytes.fromhex('f0b591b00d460446')
PROGRAM_ADDR = 0x86370000
MAX_BYTES = 0x40000


def read_bytes(svc, addr, n):
    aligned = addr & ~0x3FF
    skip = addr - aligned
    out = b''
    for off in range(0, skip + n, 1024):
        r = svc.exchange(S.build_0x5c(aligned + off))
        out += r[4:1028]
    return out[skip:skip + n]


def write_bytes(svc, addr, data):
    if len(data) % 2:
        data += b'\x00'
    import struct
    for i in range(0, len(data), 2):
        svc.exchange_write(S.build_0x9c(addr + i, struct.unpack_from('<H', data, i)[0]))


def hook_bytes(target):
    import struct
    return bytes.fromhex('dff800f0') + struct.pack('<I', target | 1)


def try_connect():
    try:
        return S.Service(settle=0.002)
    except SystemExit:
        return None


def load(svc, data):
    write_bytes(svc, PROGRAM_ADDR, data)
    write_bytes(svc, HOOK, hook_bytes(PROGRAM_ADDR))
    back = read_bytes(svc, PROGRAM_ADDR, len(data))
    hook = read_bytes(svc, HOOK, 8)
    return back == data and hook == hook_bytes(PROGRAM_ADDR)


def restore(svc):
    write_bytes(svc, HOOK, HOOK_ORIG)
    write_bytes(svc, PROGRAM_ADDR, b'\x00' * 64)
    return read_bytes(svc, HOOK, len(HOOK_ORIG)) == HOOK_ORIG


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', help='program file (raw Thumb)')
    ap.add_argument('--once', action='store_true', help='exit after one successful load')
    ap.add_argument('--restore', action='store_true', help='restore the hook instead of loading')
    ap.add_argument('--interval', type=float, default=3.0)
    args = ap.parse_args()

    if not args.restore and not args.file:
        ap.error('--file is required unless --restore is used')

    data = None
    if args.file:
        data = open(args.file, 'rb').read()
        if not data or len(data) > MAX_BYTES:
            print(json.dumps({'ok': False, 'error': 'file empty or larger than 256 KiB'}))
            return 1

    print(json.dumps({'waiting': True, 'file': args.file, 'restore': args.restore}), flush=True)
    while True:
        svc = try_connect()
        if not svc:
            time.sleep(args.interval)
            continue
        try:
            if args.restore:
                ok = restore(svc)
                print(json.dumps({'ok': ok, 'action': 'restore'}), flush=True)
            else:
                ok = load(svc, data)
                print(json.dumps({'ok': ok, 'action': 'load', 'bytes': len(data),
                                  'program': hex(PROGRAM_ADDR)}), flush=True)
            if args.once:
                return 0 if ok else 1
        except Exception as exc:
            print(json.dumps({'ok': False, 'error': str(exc)}), flush=True)
            if args.once:
                return 1
        finally:
            svc.close()
        time.sleep(args.interval)


if __name__ == '__main__':
    raise SystemExit(main())
