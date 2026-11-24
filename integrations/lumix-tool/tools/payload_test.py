"""Inject a tiny Thumb payload into S5 RAM and hook a function to run it.

Test payload: writes 0xDEADBEEF to 0x8F300000, then returns 0.
Hook: 0x8647994C (focus-sound wrapper) is replaced with `ldr.w pc,[pc,#0]`
      + an absolute word, so lr is preserved and the payload returns to caller.

Usage:
  python tools/payload_test.py apply     # write payload + patch hook, clear marker
  python tools/payload_test.py check     # read the marker
  python tools/payload_test.py restore   # restore the hook bytes
"""
import sys, struct, json

sys.path.insert(0, 'tools')
import s5svc as S

HOOK = 0x8647994C
HOOK_ORIG = bytes.fromhex('f0b591b00d460446')  # push/sub/mov r5/mov r4
# Zero hole inside the program image -> executable page, 256 KiB available.
PAYLOAD = 0x86370000
# Kept for the fallback test in the ECDSA verifier's code area.
VERIFIER = 0x868C08C6
VERIFIER_ORIG = bytes.fromhex(
    '70b5b0b00d461446064620220146684601f662ee202206f1200108a801f65cee'
    '012110a80cf0f8fe2022294618a801f6deec2022214620a801f6daec202204f1')
MARKER = 0x8F300000
MARKER_VAL = 0xDEADBEEF

# Thumb payload (20 bytes): marker = 0xDEADBEEF; r0 = 0; return.
PAYLOAD_BYTES = bytes.fromhex(
    '4bf6ef62'  # movw r2, #0xBEEF
    'cdf6ad62'  # movt r2, #0xDEAD
    '40f20003'  # movw r3, #0x0000
    'c8f63073'  # movt r3, #0x8F30
    '1a60'      # str  r2, [r3]
    '0020'      # movs r0, #0
    '7047'      # bx   lr
)


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
        data = data + b'\x00'
    for i in range(0, len(data), 2):
        val = struct.unpack_from('<H', data, i)[0]
        svc.exchange_write(S.build_0x9c(addr + i, val))


def cmd_apply():
    svc = open_svc()
    try:
        original = read_bytes(svc, HOOK, len(HOOK_ORIG))
        write_bytes(svc, MARKER, b'\x00' * 8)
        write_bytes(svc, PAYLOAD, PAYLOAD_BYTES)
        # ldr.w pc,[pc,#0] ; .word PAYLOAD|1
        hook = bytes.fromhex('dff800f0') + struct.pack('<I', PAYLOAD | 1)
        write_bytes(svc, HOOK, hook)
        back = read_bytes(svc, PAYLOAD, len(PAYLOAD_BYTES))
        check = read_bytes(svc, HOOK, len(hook))
        print(json.dumps({
            'ok': back == PAYLOAD_BYTES and check == hook,
            'hook_was': original.hex(),
            'payload': back.hex(),
            'hook_now': check.hex(),
        }))
    finally:
        svc.close()


def cmd_check():
    svc = open_svc()
    try:
        raw = read_bytes(svc, MARKER, 8)
        val = struct.unpack_from('<I', raw, 0)[0]
        print(json.dumps({'ok': True, 'marker': '0x%08X' % val,
                          'executed': val == MARKER_VAL, 'raw': raw.hex()}))
    finally:
        svc.close()


def cmd_restore():
    svc = open_svc()
    try:
        write_bytes(svc, HOOK, HOOK_ORIG)
        write_bytes(svc, PAYLOAD, b'\x00' * len(PAYLOAD_BYTES))
        back = read_bytes(svc, HOOK, len(HOOK_ORIG))
        area = read_bytes(svc, PAYLOAD, len(PAYLOAD_BYTES))
        print(json.dumps({'ok': back == HOOK_ORIG and area == b'\x00' * len(PAYLOAD_BYTES),
                          'hook': back.hex(), 'area': area.hex()}))
    finally:
        svc.close()


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    {'apply': cmd_apply, 'check': cmd_check, 'restore': cmd_restore}.get(cmd, cmd_check)()
