import sys
import time

from usb_link import LumixServiceUSB, wt, winusb, kernel32

ops = [int(x, 16) for x in sys.argv[1:]]


def probe(u, op):
    p = bytearray(1030)
    p[0] = 0x01
    p[1] = 0x00
    p[2] = 0xFF
    p[3] = op
    p[4:8] = (0).to_bytes(4, "little")
    p[8:12] = (0x400).to_bytes(4, "little")
    p[1028] = sum(p[1:1028]) & 0xFF
    p[1029] = 0x00
    to = wt.ULONG(200)
    for ep in (0x01, 0x82):
        winusb.WinUsb_SetPipePolicy(u.husb, ctypes_cubyte(ep), wt.ULONG(3), wt.ULONG(4), ctypes_byref(to))
    try:
        u._ctrl(0)
        u._write(bytes(p))
        u._ctrl(1)
        t = u._read(1)
        u._ctrl(1)
        rx = u._read(1030)
        return f"type={t.hex()} len={len(rx)} op={rx[3]:#04x} head={rx[4:20].hex()}"
    except Exception as e:
        return f"ERR {str(e)[:70]}"


def ctypes_cubyte(x):
    import ctypes
    return ctypes.c_ubyte(x)


def ctypes_byref(x):
    import ctypes
    return ctypes.byref(x)


with LumixServiceUSB(timeout_ms=200) as u:
    for op in ops:
        t0 = time.time()
        try:
            r = probe(u, op)
        except Exception as e:
            r = f"FATAL {str(e)[:60]}"
        print(f"op {op:#04x}: {r}  ({time.time()-t0:.2f}s)", flush=True)
