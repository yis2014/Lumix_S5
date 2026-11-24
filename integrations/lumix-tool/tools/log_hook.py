"""Install/remove a logging detour on GOT_File_Open to capture its arguments.

The detour stores r0..r3 for up to 64 calls at:
  0x8F302000  counter
  0x8F302100  entries (16 bytes each: r0, r1, r2, r3)

Usage:
  python tools/log_hook.py install
  python tools/log_hook.py read
  python tools/log_hook.py restore
  python tools/log_hook.py clear
"""
import sys, struct, json, subprocess, os

sys.path.insert(0, 'tools')
import s5svc as S

HOOK = 0x87F4C602
HOOK_ORIG = bytes.fromhex('2de9f84f0d460446')   # push.w / mov r5,r1 / mov r4,r0
PROGRAM = 0x86370000
PROGRAM_FILE = os.path.join('out', 'prog_loghook2.bin')
COUNTER = 0x8F302000
ENTRIES = 0x8F302100


def open_svc():
    try:
        return S.Service(settle=0.002)
    except SystemExit:
        print(json.dumps({'ok': False, 'error': 'camera not in service mode'}))
        raise SystemExit


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
    for i in range(0, len(data), 2):
        svc.exchange_write(S.build_0x9c(addr + i, struct.unpack_from('<H', data, i)[0]))


def hook_patch(target):
    return bytes.fromhex('dff800f0') + struct.pack('<I', target | 1)


def cmd_install():
    data = open(PROGRAM_FILE, 'rb').read()
    svc = open_svc()
    try:
        write_bytes(svc, PROGRAM, data)
        write_bytes(svc, COUNTER, b'\x00' * 4)
        write_bytes(svc, HOOK, hook_patch(PROGRAM))
        ok_prog = read_bytes(svc, PROGRAM, len(data)) == data
        ok_hook = read_bytes(svc, HOOK, 8) == hook_patch(PROGRAM)
        print(json.dumps({'ok': ok_prog and ok_hook, 'program': len(data),
                          'hook_was': HOOK_ORIG.hex()}))
    finally:
        svc.close()


def cmd_read():
    svc = open_svc()
    try:
        count = struct.unpack('<I', read_bytes(svc, COUNTER, 4))[0]
        count = min(count, 64) if count <= 64 else 64
        raw = read_bytes(svc, ENTRIES, count * 16) if count else b''
        entries = []
        for i in range(count):
            r0, r1, r2, r3 = struct.unpack_from('<4I', raw, i * 16)
            entries.append({'call': i, 'r0': '0x%08X' % r0, 'r1': '0x%08X' % r1,
                            'r2': '0x%08X' % r2, 'r3': '0x%08X' % r3})
        print(json.dumps({'ok': True, 'count': count, 'entries': entries[:32]}))
    finally:
        svc.close()


def cmd_restore():
    svc = open_svc()
    try:
        write_bytes(svc, HOOK, HOOK_ORIG)
        write_bytes(svc, PROGRAM, b'\x00' * 64)
        ok = read_bytes(svc, HOOK, len(HOOK_ORIG)) == HOOK_ORIG
        print(json.dumps({'ok': ok, 'hook': read_bytes(svc, HOOK, 8).hex()}))
    finally:
        svc.close()


def cmd_clear():
    svc = open_svc()
    try:
        write_bytes(svc, COUNTER, b'\x00' * 4)
        print(json.dumps({'ok': True}))
    finally:
        svc.close()


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'read'
    {'install': cmd_install, 'read': cmd_read, 'restore': cmd_restore,
     'clear': cmd_clear}.get(cmd, cmd_read)()
