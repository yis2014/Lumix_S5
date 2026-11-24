"""Load a raw Thumb program into S5 RAM and hook a function to run it.

The program is loaded at PROGRAM_ADDR and called with the hook's registers
(r0/r1 preserved). It must return with `bx lr`.

Usage:
  python tools/load_program.py push <file>     # write program + patch hook
  python tools/load_program.py restore         # restore the original hook bytes
  python tools/load_program.py verify <file>   # compare RAM with the file
"""
import sys, struct, json

sys.path.insert(0, 'tools')
import s5svc as S

HOOK = 0x8647994C                       # focus-sound wrapper (called on half-press)
HOOK_ORIG = bytes.fromhex('f0b591b00d460446')   # push/sub/mov r5/mov r4
# 256 KiB zero hole inside the program image (0x86360000..0x863B0000), so the
# page is executable exactly like the surrounding code.
PROGRAM_ADDR = 0x86370000
MAX_BYTES = 0x40000                     # 256 KiB up to 0x863B0000


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


def hook_bytes(target):
    # ldr.w pc, [pc, #0] ; .word target|1  -> tail jump, lr preserved
    return bytes.fromhex('dff800f0') + struct.pack('<I', target | 1)


def cmd_push(path):
    data = open(path, 'rb').read()
    if not data or len(data) > MAX_BYTES:
        print(json.dumps({'ok': False, 'error': 'file empty or too large'}))
        return
    svc = open_svc()
    try:
        original = read_bytes(svc, HOOK, len(HOOK_ORIG))
        write_bytes(svc, PROGRAM_ADDR, data)
        write_bytes(svc, HOOK, hook_bytes(PROGRAM_ADDR))
        back = read_bytes(svc, PROGRAM_ADDR, len(data))
        hook_now = read_bytes(svc, HOOK, 8)
        print(json.dumps({
            'ok': back == data and hook_now == hook_bytes(PROGRAM_ADDR),
            'bytes': len(data),
            'program': hex(PROGRAM_ADDR),
            'hook_was': original.hex(),
            'hook_now': hook_now.hex(),
        }))
    finally:
        svc.close()


def cmd_restore():
    svc = open_svc()
    try:
        write_bytes(svc, HOOK, HOOK_ORIG)
        back = read_bytes(svc, HOOK, len(HOOK_ORIG))
        print(json.dumps({'ok': back == HOOK_ORIG, 'hook': back.hex()}))
    finally:
        svc.close()


def cmd_verify(path):
    data = open(path, 'rb').read()
    svc = open_svc()
    try:
        back = read_bytes(svc, PROGRAM_ADDR, len(data))
        first = next((i for i in range(len(data)) if back[i] != data[i]), None)
        print(json.dumps({'ok': back == data, 'bytes': len(data),
                          'first_diff': first, 'ram_head': back[:16].hex()}))
    finally:
        svc.close()


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'push':
        cmd_push(sys.argv[2])
    elif cmd == 'verify':
        cmd_verify(sys.argv[2])
    elif cmd == 'restore':
        cmd_restore()
    else:
        print(__doc__)
