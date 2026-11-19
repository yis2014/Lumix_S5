import numpy as np
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

F = open(r"E:\desktop\LUMIX\S5___V29.bin", "rb").read()
PT = open(r"E:\desktop\LUMIX\program_0x86280000.bin", "rb").read()

KEY = b"WZdHXAXgu7Cn691V"
print("key len", len(KEY), KEY)

PROG_OFF = 97280 + 0x200
ct = F[PROG_OFF:PROG_OFF + 4096]
hdr = F[97280:97280 + 0x200]
iv_hdr = hdr[0x80:0x90]
print("partition header IV:", iv_hdr.hex())


def ctr_dec(key, iv, data):
    c = Cipher(algorithms.AES(key), modes.CTR(iv))
    d = c.decryptor()
    return d.update(data)


def inv32(b):
    a = np.frombuffer(b, dtype="<u4")
    return (~a).tobytes()


for iv_name, iv in (("zero", bytes(16)), ("hdr", iv_hdr)):
    dec = ctr_dec(KEY, iv, ct)
    for variant, dd in (("raw", dec), ("inv32", inv32(dec))):
        for pt_off in (0, 0x200, 0x1000):
            pt = PT[pt_off:pt_off + 4096]
            match = sum(a == b for a, b in zip(dd, pt)) / len(pt)
            if match > 0.05:
                print(f"HIT iv={iv_name} {variant} pt_off={pt_off:#x} match={match:.3f}")
        print(f"iv={iv_name} {variant} head={dd[:32].hex()}")
