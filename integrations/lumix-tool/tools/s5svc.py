"""Read-only client for the Lumix vendor USB service interface (04da:2370).

Protocol reconstructed from the public Lumix firmware research
(flickering-star/lumix-firmware-research, gavenomix/lumix-gx8-usb-service).

Only read opcodes are implemented:
    0x38  settings word read   (area 0x20, index u16)
    0x70  program-relative word read (index u32)   -- dry-run only, can wedge some bodies
    0x5C  absolute 1 KiB block read (start, end)

The write opcode 0x9C is rejected by name and never built.

Transport: WinUSB via ctypes (no Python packages required).
Requires WinUSB bound to the 04DA:2370 interface (Zadig).

Usage:
    python tools/s5svc.py identify
    python tools/s5svc.py block 0x80000000 --out dump_80000000.bin
    python tools/s5svc.py probe-zero
    python tools/s5svc.py selftest
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
import time
import winreg

VID = 0x04DA
PID = 0x2370
EP_OUT = 0x01
EP_IN = 0x82
TIMEOUT_MS = 1500
SETTLE_S = 0.10

REQUEST_KIND = 0x08
BLOCK_KIND = 0x01
IDENTIFY_AREA = 0x20
IDENTIFY_FIRST = 0x3F80
IDENTIFY_LAST = 0x3F8F
BLOCK_DATA_LEN = 1024
BLOCK_FRAME_LEN = 1030
READ_OPCODES = frozenset({0x35, 0x38, 0x5C, 0x75, 0x9B})

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

GUID_USB_DEVICE = "{a5dcbf10-6530-11d2-901f-00c04fb951ed}"


class WINUSB_SETUP_PACKET(ctypes.Structure):
    _fields_ = [
        ("RequestType", ctypes.c_ubyte),
        ("Request", ctypes.c_ubyte),
        ("Value", ctypes.c_ushort),
        ("Index", ctypes.c_ushort),
        ("Length", ctypes.c_ushort),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
winusb = ctypes.WinDLL("winusb", use_last_error=True)

CreateFileW = kernel32.CreateFileW
CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
                        wt.DWORD, wt.DWORD, wt.HANDLE]
CreateFileW.restype = wt.HANDLE

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wt.HANDLE]
CloseHandle.restype = wt.BOOL

WinUsb_Initialize = winusb.WinUsb_Initialize
WinUsb_Initialize.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
WinUsb_Initialize.restype = wt.BOOL

WinUsb_Free = winusb.WinUsb_Free
WinUsb_Free.argtypes = [ctypes.c_void_p]
WinUsb_Free.restype = wt.BOOL

WinUsb_ControlTransfer = winusb.WinUsb_ControlTransfer
WinUsb_ControlTransfer.argtypes = [ctypes.c_void_p, WINUSB_SETUP_PACKET,
                                   ctypes.c_void_p, wt.ULONG,
                                   ctypes.POINTER(wt.ULONG), ctypes.c_void_p]
WinUsb_ControlTransfer.restype = wt.BOOL

WinUsb_WritePipe = winusb.WinUsb_WritePipe
WinUsb_WritePipe.argtypes = [ctypes.c_void_p, ctypes.c_ubyte, ctypes.c_void_p,
                             wt.ULONG, ctypes.POINTER(wt.ULONG), ctypes.c_void_p]
WinUsb_WritePipe.restype = wt.BOOL

WinUsb_ReadPipe = winusb.WinUsb_ReadPipe
WinUsb_ReadPipe.argtypes = [ctypes.c_void_p, ctypes.c_ubyte, ctypes.c_void_p,
                            wt.ULONG, ctypes.POINTER(wt.ULONG), ctypes.c_void_p]
WinUsb_ReadPipe.restype = wt.BOOL

WinUsb_SetPipePolicy = winusb.WinUsb_SetPipePolicy
WinUsb_SetPipePolicy.argtypes = [ctypes.c_void_p, ctypes.c_ubyte, wt.ULONG,
                                 wt.ULONG, ctypes.c_void_p]
WinUsb_SetPipePolicy.restype = wt.BOOL

PIPE_TRANSFER_TIMEOUT = 0x03


def err(msg):
    return "%s (GetLastError=%d)" % (msg, ctypes.get_last_error())


def find_device_path():
    """Build the WinUSB device interface path from the USB enum registry key."""
    root = r"SYSTEM\CurrentControlSet\Enum\USB\VID_%04X&PID_%04X" % (VID, PID)
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root) as k:
        n = 0
        instances = []
        while True:
            try:
                instances.append(winreg.EnumKey(k, n))
            except OSError:
                break
            n += 1
    if not instances:
        raise SystemExit("no %04X:%04X instance in registry" % (VID, PID))
    inst = instances[0]
    guid = GUID_USB_DEVICE
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            root + "\\" + inst + r"\Device Parameters") as k:
            v, _ = winreg.QueryValueEx(k, "DeviceInterfaceGUIDs")
            if v:
                guid = v[0]
    except OSError:
        pass
    return r"\\?\USB#VID_%04X&PID_%04X#%s#%s" % (VID, PID, inst, guid)


class Service:
    def __init__(self, settle=SETTLE_S):
        path = find_device_path()
        print("device path:", path)
        self.settle = settle
        self.file = CreateFileW(path, GENERIC_READ | GENERIC_WRITE,
                                FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                                OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
        if self.file == INVALID_HANDLE_VALUE or not self.file:
            raise SystemExit(err("CreateFile failed - is WinUSB bound to 04DA:2370 and camera in temporary service mode "
                                 "(right dial P, left dial Single, hold Playback + AF ON and power on)?"))
        self.usb = ctypes.c_void_p()
        if not WinUsb_Initialize(self.file, ctypes.byref(self.usb)):
            raise SystemExit(err("WinUsb_Initialize failed - wrong driver on the interface?"))
        for ep in (EP_OUT, EP_IN):
            t = wt.ULONG(TIMEOUT_MS)
            WinUsb_SetPipePolicy(self.usb, ep, PIPE_TRANSFER_TIMEOUT,
                                 ctypes.sizeof(t), ctypes.byref(t))
        print("interface opened")

    def close(self):
        try:
            WinUsb_Free(self.usb)
        except Exception:
            pass
        try:
            CloseHandle(self.file)
        except Exception:
            pass

    def ctrl(self, index):
        setup = WINUSB_SETUP_PACKET(0x40, 0x00, 0, index, 0)
        transferred = wt.ULONG(0)
        if not WinUsb_ControlTransfer(self.usb, setup, None, 0,
                                      ctypes.byref(transferred), None):
            raise RuntimeError(err("control transfer (wIndex=%d) failed" % index))

    def write(self, data):
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        written = wt.ULONG(0)
        if not WinUsb_WritePipe(self.usb, EP_OUT, buf, len(data),
                                ctypes.byref(written), None):
            raise RuntimeError(err("bulk OUT failed"))
        if written.value != len(data):
            raise RuntimeError("short bulk OUT %d/%d" % (written.value, len(data)))

    def read(self, size):
        buf = ctypes.create_string_buffer(size)
        got = wt.ULONG(0)
        if not WinUsb_ReadPipe(self.usb, EP_IN, buf, size,
                               ctypes.byref(got), None):
            raise RuntimeError(err("bulk IN failed"))
        return buf.raw[:got.value]

    def exchange(self, frame, allow_write=False):
        if frame[3] == 0x9C:
            if not allow_write:
                raise SystemExit("REFUSED: 0x9C is the write opcode")
        elif frame[3] not in READ_OPCODES:
            raise SystemExit("REFUSED: opcode 0x%02X not allow-listed" % frame[3])
        if frame[-2] != (sum(frame[1:-2]) & 0xFF) or frame[-1] != 0:
            raise SystemExit("REFUSED: bad checksum/terminator")
        size = BLOCK_FRAME_LEN if frame[3] == 0x5C else 16
        self.ctrl(0)
        self.write(frame)
        time.sleep(self.settle)
        self.ctrl(1)
        kind = self.read(1)
        if len(kind) != 1 or kind[0] != frame[0]:
            raise RuntimeError("type byte %s != 0x%02X" % (kind.hex(), frame[0]))
        self.ctrl(1)
        return self.read(size)

    def exchange_write(self, frame):
        return self.exchange(frame, allow_write=True)


def frame_checksum(frame):
    return sum(frame[1:-2]) & 0xFF


def build_0x38(index, area=IDENTIFY_AREA):
    f = bytearray(16)
    f[0] = REQUEST_KIND
    f[1] = 0x00
    f[2] = 0xFF
    f[3] = 0x38
    f[4] = index & 0xFF
    f[5] = (index >> 8) & 0xFF
    f[6] = area
    f[14] = frame_checksum(f)
    f[15] = 0
    return bytes(f)


def build_0x35(index, selector):
    """Indexed 2-byte buffer read (GX9-era)."""
    f = bytearray(16)
    f[0] = REQUEST_KIND
    f[1] = 0x00
    f[2] = 0xFF
    f[3] = 0x35
    f[4] = index & 0xFF
    f[5] = (index >> 8) & 0xFF
    f[6] = selector
    f[14] = frame_checksum(f)
    f[15] = 0
    return bytes(f)


def build_0x9b(addr):
    """Absolute 2-byte read (GX9-era)."""
    f = bytearray(16)
    f[0] = REQUEST_KIND
    f[1] = 0x00
    f[2] = 0xFF
    f[3] = 0x9B
    f[4:8] = struct.pack("<I", addr)
    f[14] = frame_checksum(f)
    f[15] = 0
    return bytes(f)


def build_0x75(index):
    """RAM-relative 2-byte read: address = base + 2*index (GX9-era)."""
    f = bytearray(16)
    f[0] = REQUEST_KIND
    f[1] = 0x00
    f[2] = 0xFF
    f[3] = 0x75
    f[4:8] = struct.pack("<I", index)
    f[14] = frame_checksum(f)
    f[15] = 0
    return bytes(f)


def build_0x5c(addr, length=BLOCK_DATA_LEN):
    if addr % 1024 or addr < 0 or addr + length > 0xFFFFFFFF:
        raise ValueError("address must be 1024-aligned and inside u32")
    f = bytearray(BLOCK_FRAME_LEN)
    f[0] = BLOCK_KIND
    f[1] = 0x00
    f[2] = 0xFF
    f[3] = 0x5C
    f[4:8] = struct.pack("<I", addr)
    f[8:12] = struct.pack("<I", addr + length)
    f[1028] = frame_checksum(f)
    f[1029] = 0
    return bytes(f)


def cmd_identify(svc):
    data = bytearray()
    for idx in range(IDENTIFY_FIRST, IDENTIFY_LAST + 1):
        reply = svc.exchange(build_0x38(idx))
        ok = (len(reply) == 16 and reply[0] == 0x08 and reply[1:3] == b"\x00\xff"
              and reply[3] == 0x36 and reply[6:14] == b"\x00" * 8
              and reply[14] == (sum(reply[1:-2]) & 0xFF) and reply[15] == 0)
        if not ok:
            print("index 0x%04X reply invalid: %s" % (idx, reply.hex()))
            continue
        data += reply[4:6]
    print("identify bytes (%d):" % len(data), data.hex())
    print("ascii:", "".join(chr(b) if 32 <= b < 127 else "." for b in data))


def cmd_block(svc, addr, out):
    reply = svc.exchange(build_0x5c(addr))
    ok = (len(reply) == BLOCK_FRAME_LEN and reply[0] == BLOCK_KIND
          and reply[1:3] == b"\x00\xff" and reply[3] == 0x05
          and reply[1028] == (sum(reply[1:-2]) & 0xFF) and reply[1029] == 0)
    print("block 0x%08X: %s" % (addr, "PASS" if ok else "FAIL"))
    if len(reply) != BLOCK_FRAME_LEN:
        print("  length", len(reply))
        return
    data = reply[4:4 + BLOCK_DATA_LEN]
    print("  first 64:", data[:64].hex())
    print("  ascii   :", "".join(chr(b) if 32 <= b < 127 else "." for b in data[:64]))
    if out:
        with open(out, "wb") as fh:
            fh.write(data)
        print("  saved:", out)


def cmd_probe_zero(svc):
    f = bytearray(BLOCK_FRAME_LEN)
    f[0] = BLOCK_KIND
    f[1] = 0x00
    f[2] = 0xFF
    f[3] = 0x5C
    f[1028] = frame_checksum(f)
    f[1029] = 0
    reply = svc.exchange(bytes(f))
    print("probe-zero reply:", reply[:8].hex(), "...", len(reply), "bytes")


def cmd_buf(svc, selector, start, count):
    for index in range(start, start + count):
        reply = svc.exchange(build_0x35(index, selector))
        if len(reply) >= 6 and reply[3] == 0x36:
            print("sel 0x%02X idx 0x%04X -> %s" % (selector, index, reply[4:6].hex()))
        else:
            print("sel 0x%02X idx 0x%04X -> %s (no 0x36)" % (selector, index, reply.hex()))


def cmd_word(svc, addr):
    reply = svc.exchange(build_0x9b(addr))
    print("0x9b 0x%08X -> %s" % (addr, reply.hex()))


def cmd_rel(svc, index):
    reply = svc.exchange(build_0x75(index))
    print("0x75 idx 0x%X -> %s" % (index, reply.hex()))


def cmd_dump(svc, start, end, out):
    import os
    if os.path.exists(out) and os.path.getsize(out) > 0:
        raise SystemExit("refusing to overwrite non-empty %s" % out)
    total = end - start
    addr = start
    with open(out, "wb") as fh:
        n = 0
        while addr < end:
            reply = svc.exchange(build_0x5c(addr))
            ok = (len(reply) == BLOCK_FRAME_LEN and reply[0] == BLOCK_KIND
                  and reply[1:3] == b"\x00\xff" and reply[3] == 0x05
                  and reply[1028] == (sum(reply[1:-2]) & 0xFF) and reply[1029] == 0)
            if not ok:
                print("FAIL at 0x%08X: %s" % (addr, reply[:8].hex()))
                break
            fh.write(reply[4:4 + BLOCK_DATA_LEN])
            fh.flush()
            addr += BLOCK_DATA_LEN
            n += 1
            if n % 64 == 0:
                print("  %d / %d KiB" % ((addr - start) // 1024, total // 1024))
    print("stopped at 0x%08X" % addr)


def build_0x9c(addr, value):
    """Absolute 2-byte RAM write (GX9-measured opcode 0x9C)."""
    f = bytearray(16)
    f[0] = REQUEST_KIND
    f[1] = 0x00
    f[2] = 0xFF
    f[3] = 0x9C
    f[4:8] = struct.pack("<I", addr)
    f[8] = value & 0xFF
    f[9] = (value >> 8) & 0xFF
    f[14] = frame_checksum(f)
    f[15] = 0
    return bytes(f)


def cmd_write16(svc, addr, value):
    ack = svc.exchange_write(build_0x9c(addr, value))
    print("write 0x%08X <- 0x%04X  ack=%s" % (addr, value, ack.hex()))
    rb = svc.exchange(build_0x9b(addr))
    got = struct.unpack_from("<H", rb, 4)[0] if len(rb) >= 6 and rb[3] == 0x36 else None
    print("readback 0x%08X = %s  %s" % (addr, ("0x%04X" % got) if got is not None else rb.hex(),
                                        "OK" if got == value else "MISMATCH"))


def cmd_dim(svc, addr, values):
    for i, v in enumerate(values):
        a = addr + 2 * i
        svc.exchange_write(build_0x9c(a, v))


def read_mem(svc, addr, length):
    out = bytearray()
    a = addr
    end = addr + length
    while a < end:
        r = svc.exchange(build_0x5c(a))
        if not (len(r) == BLOCK_FRAME_LEN and r[3] == 0x05):
            raise RuntimeError("block read failed at 0x%08X: %s" % (a, r[:8].hex()))
        out += r[4:4 + BLOCK_DATA_LEN]
        a += BLOCK_DATA_LEN
    return bytes(out[:length])


def png_rgba(path, w, h, rgba):
    import zlib
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgba[y * w * 4:(y + 1) * w * 4]

    def chunk(t, d):
        return (struct.pack(">I", len(d)) + t + d +
                struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
           chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


OSD_PLANE_A = 0x8DC00000
OSD_STRIDE = 4096


def cmd_ospng(svc, out, base, height):
    data = read_mem(svc, base, height * OSD_STRIDE)
    rgba = bytearray(len(data))
    for i in range(0, len(data), 4):
        a, b, g, r = data[i], data[i + 1], data[i + 2], data[i + 3]
        if a == 0 and b == 0 and g == 0 and r == 0:
            rgba[i:i + 4] = bytes((18, 18, 22, 255))
        else:
            rgba[i:i + 4] = bytes((r, g, b, a))
    png_rgba(out, 1024, height, rgba)
    print("saved", out, "(%dx%d from 0x%08X)" % (1024, height, base))


def cmd_osfill(svc, x, y, w, h, abgr):
    a = (abgr >> 24) & 0xFF
    b = (abgr >> 16) & 0xFF
    g = (abgr >> 8) & 0xFF
    r = abgr & 0xFF
    n = 0
    for yy in range(y, y + h):
        row = OSD_PLANE_A + yy * OSD_STRIDE
        for xx in range(x, x + w):
            addr = row + xx * 4
            svc.exchange_write(build_0x9c(addr, a | (b << 8)))
            svc.exchange_write(build_0x9c(addr + 2, g | (r << 8)))
            n += 1
    print("filled %d px at (%d,%d) %dx%d argb=0x%08X" % (n, x, y, w, h, abgr))


def selftest():
    f = build_0x38(0x3F80)
    assert f[:7] == bytes([0x08, 0x00, 0xFF, 0x38, 0x80, 0x3F, 0x20]), f.hex()
    assert f[14] == frame_checksum(f) and f[15] == 0
    b = build_0x5c(0x80000000)
    assert len(b) == 1030 and b[3] == 0x5C
    assert struct.unpack("<I", b[4:8])[0] == 0x80000000
    assert struct.unpack("<I", b[8:12])[0] == 0x80000400
    assert b[1028] == frame_checksum(b) and b[1029] == 0
    print("selftest ok")
    print("0x38 frame:", f.hex())
    print("0x5C head :", b[:16].hex())


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return
    cmd = argv[1]
    if cmd == "selftest":
        selftest()
        return
    settle = SETTLE_S
    if "--settle" in argv:
        i = argv.index("--settle")
        settle = float(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    svc = Service(settle)
    try:
        if cmd == "identify":
            cmd_identify(svc)
        elif cmd == "block":
            addr = int(argv[2], 0)
            out = argv[4] if len(argv) > 4 and argv[3] == "--out" else None
            cmd_block(svc, addr, out)
        elif cmd == "probe-zero":
            cmd_probe_zero(svc)
        elif cmd == "buf":
            cmd_buf(svc, int(argv[2], 0), int(argv[3], 0),
                    int(argv[4], 0) if len(argv) > 4 else 1)
        elif cmd == "word":
            cmd_word(svc, int(argv[2], 0))
        elif cmd == "rel":
            cmd_rel(svc, int(argv[2], 0))
        elif cmd == "ospng":
            cmd_ospng(svc, argv[2], int(argv[3],0) if len(argv)>3 else OSD_PLANE_A, int(argv[4],0) if len(argv)>4 else 480)
        elif cmd == "osfill":
            cmd_osfill(svc, int(argv[2],0), int(argv[3],0), int(argv[4],0), int(argv[5],0), int(argv[6],0))
        elif cmd == "write16":
            cmd_write16(svc, int(argv[2], 0), int(argv[3], 0))
        elif cmd == "dump":
            cmd_dump(svc, int(argv[2], 0), int(argv[3], 0), argv[4])
        else:
            print(__doc__)
    finally:
        svc.close()


if __name__ == "__main__":
    main(sys.argv)




