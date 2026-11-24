"""Generic argument tracer: hook a function, log r0..r3 for each call.

Unlike the ad-hoc scripts, this one takes the hook address and the continuation
address, assembles the logger with keystone, and verifies both write-backs.

Usage:
  python tools/trace_hook.py install <hook-addr> <return-addr> [--size 8]
  python tools/trace_hook.py read
  python tools/trace_hook.py restore <hook-addr> <original-hex>
  python tools/trace_hook.py clear

The logger saves r0..r3, appends them to 0x8F302100 (64 entries max), then
tail-jumps to <return-addr> with lr untouched.
"""
import sys, struct, json
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB

sys.path.insert(0, 'tools')
import s5svc as S

PROGRAM = 0x86370000
COUNTER = 0x8F302000
ENTRIES = 0x8F302100


def build_logger(ret, extra=b''):
    asm = f"""
        push {{r4-r7}}
        mov r4, r0
        mov r5, r1
        mov r6, r2
        mov r7, r3
        movw r3, #0x2000
        movt r3, #0x8F30
        ldr r2, [r3]
        cmp r2, #64
        bhs skip
        adds r2, #1
        str r2, [r3]
        subs r2, #1
        lsls r2, r2, #4
        movw r0, #0x2100
        movt r0, #0x8F30
        add r0, r0, r2
        str r4, [r0]
        str r5, [r0, #4]
        str r6, [r0, #8]
        str r7, [r0, #12]
    skip:
        mov r0, r4
        mov r1, r5
        mov r2, r6
        mov r3, r7
        pop {{r4-r7}}
    """
    ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
    enc, _ = ks.asm(asm, PROGRAM)
    body = bytes(enc)
    # append the optional original instructions, then the far jump
    tail_addr = PROGRAM + len(body) + len(extra)
    jump = f"""
        ldr.w pc, [pc, #0]
        .word {hex(ret | 1)}
    """
    enc2, _ = ks.asm(jump, tail_addr)
    return body + extra + bytes(enc2)


def enc_bw(addr, target):
    off = target - (addr + 4)
    if off < 0:
        off += 1 << 25
    s = (off >> 24) & 1
    i1 = (off >> 23) & 1
    i2 = (off >> 22) & 1
    imm10 = (off >> 12) & 0x3FF
    imm11 = (off >> 1) & 0x7FF
    j1 = 1 - (i1 ^ s)
    j2 = 1 - (i2 ^ s)
    hw1 = 0xF000 | (s << 10) | imm10
    hw2 = 0x8000 | (j1 << 13) | 0x1000 | (j2 << 11) | imm11
    return struct.pack('<HH', hw1, hw2)


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


def cmd_install(hook, ret, size):
    svc = open_svc()
    try:
        original = read_bytes(svc, hook, size)
        if ret is None:
            ret = hook + size
        # 4-byte slot: use a direct B.W (needs to be within +-16 MiB)
        offset = PROGRAM - (hook + 4)
        if size == 4 and -0x1000000 < offset < 0x1000000:
            patch = enc_bw(hook, PROGRAM)
        else:
            if size < 8:
                print(json.dumps({'ok': False, 'error': 'need 8 bytes for the far jump'}))
                return
            patch = bytes.fromhex('dff800f0') + struct.pack('<I', PROGRAM | 1) + b'\x00' * (size - 8)
        # The logger must first execute every instruction the patch overwrote.
        logger = build_logger(ret, extra=original)
        write_bytes(svc, PROGRAM, logger)
        write_bytes(svc, COUNTER, b'\x00' * 4)
        write_bytes(svc, hook, patch)
        print(json.dumps({
            'ok': read_bytes(svc, hook, size) == patch and read_bytes(svc, PROGRAM, len(logger)) == logger,
            'hook': '0x%08X' % hook, 'return': '0x%08X' % ret, 'size': size,
            'original': original.hex(), 'logger_bytes': len(logger), 'patch': patch.hex(),
        }))
    finally:
        svc.close()


def cmd_read():
    svc = open_svc()
    try:
        count = struct.unpack('<I', read_bytes(svc, COUNTER, 4))[0]
        count = min(count, 64)
        raw = read_bytes(svc, ENTRIES, count * 16) if count else b''
        entries = [{'r0': '0x%08X' % struct.unpack_from('<4I', raw, i * 16)[0],
                    'r1': '0x%08X' % struct.unpack_from('<4I', raw, i * 16)[1],
                    'r2': '0x%08X' % struct.unpack_from('<4I', raw, i * 16)[2],
                    'r3': '0x%08X' % struct.unpack_from('<4I', raw, i * 16)[3]}
                   for i in range(count)]
        print(json.dumps({'ok': True, 'count': count, 'entries': entries[:32]}))
    finally:
        svc.close()


def cmd_restore(hook, original_hex):
    svc = open_svc()
    try:
        write_bytes(svc, hook, bytes.fromhex(original_hex))
        print(json.dumps({'ok': read_bytes(svc, hook, len(original_hex) // 2).hex() == original_hex}))
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
    if cmd == 'install':
        size = 8
        if '--size' in sys.argv:
            size = int(sys.argv[sys.argv.index('--size') + 1])
        cmd_install(int(sys.argv[2], 16), int(sys.argv[3], 16), size)
    elif cmd == 'restore':
        cmd_restore(int(sys.argv[2], 16), sys.argv[3])
    elif cmd == 'clear':
        cmd_clear()
    else:
        cmd_read()
