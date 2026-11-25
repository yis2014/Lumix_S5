"""Zero-dependency WinUSB transport for Panasonic DC-S5 Service Mode (04DA:2370).

Provides:
  - Auto-discovery of USB\\VID_04DA&PID_2370 via Windows Registry DeviceClasses
  - Fast 1 KiB block read (opcode 0x5c, ~1 MiB/s, safe on unmapped addresses)
  - Verified halfword RAM write (opcode 0x9c) with automatic JSON backup & rollback
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import struct
import time
import winreg

kernel32 = ctypes.windll.kernel32
winusb = ctypes.windll.winusb

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

GUID_DEVINTERFACE_USB_DEVICE = "{a5dcbf10-6530-11d2-901f-00c04fb951ed}"


class WINUSB_SETUP_PACKET(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("RequestType", ctypes.c_ubyte),
        ("Request", ctypes.c_ubyte),
        ("Value", ctypes.c_ushort),
        ("Index", ctypes.c_ushort),
        ("Length", ctypes.c_ushort),
    ]


kernel32.CreateFileW.restype = wt.HANDLE
kernel32.CreateFileW.argtypes = [
    wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE
]


def find_dcs5_device_paths():
    """Find all WinUSB device interface paths for VID_04DA&PID_2370.

    Prefers a live SetupAPI enumeration (registry DeviceClasses entries can be stale
    after re-plug / mode switches, yielding ERROR_FILE_NOT_FOUND on CreateFileW).
    """
    live = _find_via_setupapi()
    if live:
        return live
    return _find_via_registry()


def _find_via_setupapi():
    """Enumerate present WinUSB interfaces with SetupDi* and return their real paths."""
    setupapi = ctypes.windll.setupapi
    DIGCF_PRESENT = 0x02
    DIGCF_DEVICEINTERFACE = 0x10
    INVALID_HANDLE = ctypes.c_void_p(-1).value

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

    class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("InterfaceClassGuid", GUID),
                    ("Flags", wt.DWORD), ("Reserved", ctypes.POINTER(ctypes.c_ulong))]

    def guid_from_str(s):
        parts = s.strip("{}").split("-")
        g = GUID()
        g.Data1 = int(parts[0], 16)
        g.Data2 = int(parts[1], 16)
        g.Data3 = int(parts[2], 16)
        tail = bytes.fromhex(parts[3] + parts[4])
        for i in range(8):
            g.Data4[i] = tail[i]
        return g

    guid = guid_from_str(GUID_DEVINTERFACE_USB_DEVICE)
    hdev = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )
    if not hdev or hdev == INVALID_HANDLE:
        return []

    paths = []
    try:
        idx = 0
        while True:
            did = SP_DEVICE_INTERFACE_DATA()
            did.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
            if not setupapi.SetupDiEnumDeviceInterfaces(
                hdev, None, ctypes.byref(guid), idx, ctypes.byref(did)
            ):
                break
            idx += 1
            needed = wt.DWORD(0)
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                hdev, ctypes.byref(did), None, 0, ctypes.byref(needed), None
            )
            if not needed.value:
                continue
            buf = (ctypes.c_ubyte * needed.value)()
            # SP_DEVICE_INTERFACE_DETAIL_DATA_W.cbSize: 8 on x64, 6 on x86
            ctypes.cast(buf, ctypes.POINTER(wt.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if not setupapi.SetupDiGetDeviceInterfaceDetailW(
                hdev, ctypes.byref(did), buf, needed.value, None, None
            ):
                continue
            path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
            if "vid_04da&pid_2370" in path.lower():
                paths.append(path)
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(hdev)
    return paths


def _find_via_registry():
    """Find all WinUSB device interface paths for VID_04DA&PID_2370 (legacy fallback)."""
    paths = []
    reg_key = rf"SYSTEM\CurrentControlSet\Control\DeviceClasses\{GUID_DEVINTERFACE_USB_DEVICE}"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_key) as root:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(root, i)
                    i += 1
                except OSError:
                    break
                if "vid_04da&pid_2370" in sub.lower():
                    # Convert ##?#USB#... to \\?\USB#...
                    cleaned = sub
                    if cleaned.startswith("##?#"):
                        cleaned = r"\\?\\"[:-1] + cleaned[4:]
                    paths.append(cleaned)
    except OSError:
        pass
    return paths


class LumixServiceUSB:
    BLOCK_SIZE = 1024
    FRAME_5C = 1030

    def __init__(self, path=None, timeout_ms=2000):
        candidates = [path] if path else find_dcs5_device_paths()
        if not candidates:
            raise RuntimeError(
                "No Panasonic DC-S5 (04DA:2370) found in DeviceClasses. "
                "Set right dial to P, left dial to Single, hold Playback + AF ON and power on "
                "(右转轮调到P档、左转轮调到单拍，同时按住回放+AF ON键开机进入临时服务模式，否则会一直识别成其他模式)."
            )

        last_err = None
        self.hfile = None
        self.husb = ctypes.c_void_p()
        for cand in candidates:
            hf = kernel32.CreateFileW(
                cand,
                GENERIC_READ | GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                FILE_FLAG_OVERLAPPED,
                None,
            )
            if hf == INVALID_HANDLE_VALUE or not hf:
                last_err = kernel32.GetLastError()
                continue
            husb = ctypes.c_void_p()
            if winusb.WinUsb_Initialize(wt.HANDLE(hf), ctypes.byref(husb)):
                self.hfile = hf
                self.husb = husb
                self.device_path = cand
                break
            last_err = kernel32.GetLastError()
            kernel32.CloseHandle(wt.HANDLE(hf))

        if not self.hfile:
            raise RuntimeError(f"Could not open DC-S5 WinUSB interface (last_err={last_err})")

        to = wt.ULONG(timeout_ms)
        for ep in (0x01, 0x82):
            winusb.WinUsb_SetPipePolicy(
                self.husb, ctypes.c_ubyte(ep), wt.ULONG(3), wt.ULONG(4), ctypes.byref(to)
            )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        if getattr(self, "husb", None):
            winusb.WinUsb_Free(self.husb)
            self.husb = None
        if getattr(self, "hfile", None):
            kernel32.CloseHandle(wt.HANDLE(self.hfile))
            self.hfile = None

    def _ctrl(self, wIndex):
        pkt = WINUSB_SETUP_PACKET(0x40, 0x00, 0, wIndex, 0)
        transferred = wt.ULONG(0)
        if not winusb.WinUsb_ControlTransfer(
            self.husb, pkt, None, 0, ctypes.byref(transferred), None
        ):
            raise RuntimeError(f"ControlTransfer failed: err={kernel32.GetLastError()}")

    def _write(self, data):
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        transferred = wt.ULONG(0)
        if not winusb.WinUsb_WritePipe(
            self.husb, ctypes.c_ubyte(0x01), buf, len(data), ctypes.byref(transferred), None
        ):
            raise RuntimeError(f"WritePipe failed: err={kernel32.GetLastError()}")
        return transferred.value

    def _read(self, size):
        buf = (ctypes.c_ubyte * size)()
        transferred = wt.ULONG(0)
        if not winusb.WinUsb_ReadPipe(
            self.husb, ctypes.c_ubyte(0x82), buf, size, ctypes.byref(transferred), None
        ):
            raise RuntimeError(f"ReadPipe failed: err={kernel32.GetLastError()}")
        return bytes(buf[: transferred.value])

    def read_block(self, addr, delay=0.0, retries=4):
        """Read 1024 bytes with automatic retry on transient USB failures (err=31 etc.)."""
        last = None
        for attempt in range(retries):
            try:
                return self._read_block_once(addr, delay)
            except RuntimeError as e:
                last = e
                time.sleep(0.05 * (attempt + 1))
        raise RuntimeError(f"0x5c read_block(0x{addr:08x}) failed after {retries} tries: {last}")

    def _read_block_once(self, addr, delay=0.0):
        """Read 1024 bytes from physical address `addr` using safe opcode 0x5c."""
        p = bytearray(self.FRAME_5C)
        p[0] = 0x01
        p[1] = 0x00
        p[2] = 0xFF
        p[3] = 0x5C
        p[4:8] = (addr & 0xFFFFFFFF).to_bytes(4, "little")
        p[8:12] = ((addr + self.BLOCK_SIZE) & 0xFFFFFFFF).to_bytes(4, "little")
        p[self.FRAME_5C - 2] = sum(p[1 : self.FRAME_5C - 2]) & 0xFF
        p[self.FRAME_5C - 1] = 0x00

        self._ctrl(0)
        self._write(bytes(p))
        if delay > 0:
            time.sleep(delay)
        self._ctrl(1)
        t = self._read(1)
        if t != b"\x01":
            raise RuntimeError(f"0x5c unexpected type byte: {t.hex()}")
        self._ctrl(1)
        rx = self._read(self.FRAME_5C)
        if len(rx) != self.FRAME_5C:
            raise RuntimeError(f"0x5c short frame: {len(rx)}")
        chk = sum(rx[1 : self.FRAME_5C - 2]) & 0xFF
        if rx[3] != 0x05 or rx[-2] != chk or rx[-1] != 0:
            raise RuntimeError(f"0x5c bad reply: op={rx[3]:#04x}")
        return rx[4 : 4 + self.BLOCK_SIZE]

    def read_mem(self, addr, size):
        """Read arbitrary byte range using aligned 1 KiB 0x5c block reads."""
        start_blk = addr & ~0x3FF
        end_addr = addr + size
        buf = bytearray()
        for b_addr in range(start_blk, end_addr, self.BLOCK_SIZE):
            buf += self.read_block(b_addr)
        offset = addr - start_blk
        return bytes(buf[offset : offset + size])

    def write_u16(self, addr, val_u16, delay=0.02, verify=True):
        """Write a 16-bit little-endian halfword to RAM using opcode 0x9c."""
        if addr & 1:
            raise ValueError(f"Address {addr:#010x} must be 2-byte aligned for 0x9c")
        if not (0x80000000 <= addr < 0xA0000000):
            raise ValueError(f"Address {addr:#010x} outside mapped DRAM safety window")

        p = bytearray(16)
        p[0] = 0x08
        p[1] = 0x00
        p[2] = 0xFF
        p[3] = 0x9C
        p[4:8] = addr.to_bytes(4, "little")
        p[8:10] = (val_u16 & 0xFFFF).to_bytes(2, "little")
        p[14] = sum(p[1:14]) & 0xFF
        p[15] = 0x00

        self._ctrl(0)
        self._write(bytes(p))
        if delay > 0:
            time.sleep(delay)
        self._ctrl(1)
        t = self._read(1)
        if t != b"\x08":
            raise RuntimeError(f"0x9c unexpected type byte: {t.hex()}")
        self._ctrl(1)
        rx = self._read(16)
        chk = sum(rx[1:14]) & 0xFF
        if len(rx) != 16 or rx[3] != 0x01 or rx[4] != 0x00 or rx[14] != chk:
            raise RuntimeError(f"0x9c write rejected: rx={rx.hex()}")

        if verify:
            rb = self.read_mem(addr, 2)
            got = int.from_bytes(rb, "little")
            if got != (val_u16 & 0xFFFF):
                raise RuntimeError(
                    f"0x9c verify mismatch at {addr:#010x}: wrote {val_u16:#06x}, read {got:#06x}"
                )

    def write_mem_safe(self, addr, data, backup_path=None):
        """Write even-length bytes to RAM after saving a full rollback record."""
        if addr & 1:
            raise ValueError("Start address must be 2-byte aligned")
        if len(data) & 1:
            data = data + b"\x00"

        orig = self.read_mem(addr, len(data))
        if backup_path:
            rec = {
                "timestamp": time.time(),
                "addr": hex(addr),
                "length": len(data),
                "original_hex": orig.hex(),
                "written_hex": data.hex(),
            }
            os.makedirs(os.path.dirname(os.path.abspath(backup_path)), exist_ok=True)
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(rec, f, indent=2)

        for off in range(0, len(data), 2):
            orig_u16 = struct.unpack_from("<H", orig, off)[0]
            new_u16 = struct.unpack_from("<H", data, off)[0]
            if orig_u16 != new_u16:
                self.write_u16(addr + off, new_u16, verify=True)
        return orig

    def write_sparse_pixels(self, writes_dict, backup_path=None, delay=0.001):
        """Fast batch writer for sparse {even_addr: u16_val} updates with full backup & block verify.

        Groups addresses by 1 KiB blocks so backup and post-write verification each do only one
        0x5c block read per touched 1 KiB block instead of per halfword.
        """
        if not writes_dict:
            return 0
        blocks = {}
        for addr, val in writes_dict.items():
            if addr & 1:
                raise ValueError(f"Unaligned address {addr:#x}")
            b_base = addr & ~0x3FF
            blocks.setdefault(b_base, []).append((addr, val & 0xFFFF))

        backup_records = []
        to_send = []
        for b_base in sorted(blocks):
            orig_blk = self.read_block(b_base)
            backup_records.append({"block_addr": hex(b_base), "orig_hex": orig_blk.hex()})
            for addr, val in sorted(blocks[b_base]):
                off = addr - b_base
                cur_val = struct.unpack_from("<H", orig_blk, off)[0]
                if cur_val != val:
                    to_send.append((addr, val))

        if backup_path:
            os.makedirs(os.path.dirname(os.path.abspath(backup_path)), exist_ok=True)
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump({"timestamp": time.time(), "blocks": backup_records}, f, indent=2)

        for addr, val in to_send:
            self.write_u16(addr, val, delay=delay, verify=False)

        # Block-level readback verification
        mismatches = 0
        for b_base in sorted(blocks):
            new_blk = self.read_block(b_base)
            for addr, val in blocks[b_base]:
                got = struct.unpack_from("<H", new_blk, addr - b_base)[0]
                if got != val:
                    mismatches += 1
        return len(to_send), mismatches

    def restore_sparse_backup(self, backup_path, delay=0.001):
        """Restore modified halfwords from a write_sparse_pixels JSON backup."""
        with open(backup_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        restored = 0
        for rec in data["blocks"]:
            b_base = int(rec["block_addr"], 16)
            orig_blk = bytes.fromhex(rec["orig_hex"])
            cur_blk = self.read_block(b_base)
            if cur_blk == orig_blk:
                continue
            for off in range(0, 1024, 2):
                o_val = struct.unpack_from("<H", orig_blk, off)[0]
                c_val = struct.unpack_from("<H", cur_blk, off)[0]
                if o_val != c_val:
                    self.write_u16(b_base + off, o_val, delay=delay, verify=False)
                    restored += 1
        return restored

    def rollback(self, backup_path):
        """Restore RAM contents from a JSON backup file created by write_mem_safe."""
        with open(backup_path, "r", encoding="utf-8") as f:
            rec = json.load(f)
        addr = int(rec["addr"], 16)
        orig = bytes.fromhex(rec["original_hex"])
        for off in range(0, len(orig), 2):
            u16 = struct.unpack_from("<H", orig, off)[0]
            self.write_u16(addr + off, u16, verify=True)
        return addr, len(orig)
