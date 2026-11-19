"""Capture the runtime payload AES key while the camera parses an update file.

The updater keeps the UPD header in a RAM buffer and stores a pointer to it at
partition_object+0x58. The AES key for encrypted partitions is at object+0x34.
I only ever use the 0x5c READ command, and the update is expected to be cancelled
at the confirmation prompt, so no flash write is requested by this tool.
"""
import struct
import sys
import time

from usb_link import LumixServiceUSB

START = 0x86280000
END = 0x90000000
CHUNK = 1 << 20


def find_upd_buffers(u):
    hits = []
    addr = START
    while addr < END:
        n = min(CHUNK, END - addr)
        try:
            data = u.read_mem(addr, n)
        except Exception as e:
            print(f"  read err {addr:#x}: {e}", flush=True)
            addr += n
            continue
        i = data.find(b"UPD\x00")
        while i >= 0:
            hits.append(addr + i)
            print(f"  UPD header buffer @ {addr + i:#x}", flush=True)
            i = data.find(b"UPD\x00", i + 1)
        addr += n
        if (addr - START) % (16 << 20) == 0:
            print(f"  scanned {addr:#x}", flush=True)
    return hits


def find_object(u, buf):
    """Locate the partition object whose +0x58 field points at the UPD buffer."""
    ptrs = {struct.pack("<I", buf), struct.pack("<I", buf - 0x80000000)}
    addr = START
    while addr < END:
        n = min(CHUNK, END - addr)
        try:
            data = u.read_mem(addr, n)
        except Exception:
            addr += n
            continue
        for p in ptrs:
            i = data.find(p)
            while i >= 0:
                obj = addr + i - 0x58
                print(f"  object candidate @ {obj:#x} (ptr {p.hex()})", flush=True)
                try:
                    key = u.read_mem(obj + 0x34, 0x40)
                    print(f"    [obj+0x34..0x54] = {key.hex()}", flush=True)
                except Exception as e:
                    print(f"    key read failed: {e}", flush=True)
                i = data.find(p, i + 1)
        addr += n
    return None


def main():
    passes = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    t0 = time.time()
    with LumixServiceUSB() as u:
        for k in range(passes):
            print(f"pass {k + 1}/{passes} ({time.time() - t0:.0f}s)", flush=True)
            hits = find_upd_buffers(u)
            print(f"  {len(hits)} UPD buffer(s)", flush=True)
            for h in hits:
                find_object(u, h)


if __name__ == "__main__":
    main()
