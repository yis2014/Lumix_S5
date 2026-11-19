import struct
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
from usb_link import LumixServiceUSB
from inject_test import bw

TARGET = 0x864784D8
RESUME = TARGET + 4
CAVE = 0x87086500
COUNTER = 0x87086540
ORIG = bytes.fromhex('70b50268')
BACKUP = r'E:\desktop\LUMIX\audio_counter_backup.json'

ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
asm = f'''
    push {{r0-r3}}
    movw r2, #{COUNTER & 0xffff}
    movt r2, #{COUNTER >> 16}
    ldr r3, [r2]
    adds r3, #1
    str r3, [r2]
    pop {{r0-r3}}
    push {{r4, r5, r6, lr}}
    ldr r2, [r0]
'''
hook = bytes(ks.asm(asm, addr=CAVE | 1)[0]) + bw(CAVE + len(bytes(ks.asm(asm, addr=CAVE | 1)[0])), RESUME)

def main():
    with LumixServiceUSB() as u:
        live = u.read_mem(TARGET, 4)
        if live != ORIG:
            raise RuntimeError(f'unexpected target bytes {live.hex()}')
        u.write_mem_safe(COUNTER, b'\0' * 4, backup_path=BACKUP)
        u.write_mem_safe(CAVE, hook, backup_path=BACKUP)
        u.write_mem_safe(TARGET, bw(TARGET, CAVE), backup_path=BACKUP)
        assert u.read_mem(TARGET, 4) == bw(TARGET, CAVE)
        assert u.read_mem(CAVE, len(hook)) == hook
        print('deployed', hex(TARGET), '->', hex(CAVE), 'counter=0')

if __name__ == '__main__':
    main()
