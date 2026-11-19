"""Milestone 1: draw a 2.39:1 anamorphic guide frame onto the live OSD plane.

This is a NON-DESTRUCTIVE RAM-only test:
  - Reads current OSD content (backup)
  - Writes a bright yellow guide frame (top/bottom bars + left/right pillars)
  - Screenshots the result to PNG for visual confirmation
  - Waits 3s and re-reads to test whether the camera's UI thread overwrites it

Pixel format (verified): [Alpha, Ch1, Ch2, Ch3], alpha=0xFF opaque.
Camera byte order appears to be [A, B, G, R] (Ch1=B, Ch2=G, Ch3=R).
"""
import argparse
import time

from osd_tool import write_png_rgba
from usb_link import LumixServiceUSB

PLANE_A = 0x8DC00000
PLANE_B = 0x8DF00000
STRIDE = 4096
WIDTH = 1024

# Yellow-ish guide: want RGB (255, 220, 0) -> camera order [A,B,G,R] = [FF, 00, DC, FF]
YELLOW = bytes((0xFF, 0x00, 0xDC, 0xFF))


def px_addr(base, y, x):
    return base + y * STRIDE + x * 4


def build_guide(base, y_top, y_bot, x_left, x_right):
    """Return {addr: u16} writes for a 2-px-thick box outline."""
    writes = {}
    for x in range(x_left, x_right):
        for t in (0, 1):
            for y in (y_top + t, y_bot + t):
                a = px_addr(base, y, x)
                writes[a] = int.from_bytes(YELLOW[0:2], "little")
                writes[a + 2] = int.from_bytes(YELLOW[2:4], "little")
    for y in range(y_top, y_bot + 2):
        for t in (0, 1):
            for x in (x_left + t, x_right - 1 + t):
                a = px_addr(base, y, x)
                writes[a] = int.from_bytes(YELLOW[0:2], "little")
                writes[a + 2] = int.from_bytes(YELLOW[2:4], "little")
    return writes


def screenshot_png(base, y0, h, path):
    with LumixServiceUSB() as u:
        raw = u.read_mem(base + y0 * STRIDE, h * STRIDE)
    rgba = bytearray(len(raw))
    for y in range(h):
        for x in range(WIDTH):
            off = y * STRIDE + x * 4
            a, c1, c2, c3 = raw[off], raw[off+1], raw[off+2], raw[off+3]
            if a == 0:
                rgba[off:off+4] = bytes((24, 24, 24, 255))
            else:
                rgba[off:off+4] = bytes((c3, c2, c1, a))
    write_png_rgba(path, WIDTH, h, bytes(rgba))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--y-top", type=int, default=300)
    ap.add_argument("--y-bot", type=int, default=360)
    ap.add_argument("--x-left", type=int, default=100)
    ap.add_argument("--x-right", type=int, default=924)
    ap.add_argument("--plane", type=lambda s: int(s, 0), default=PLANE_A)
    ap.add_argument("--backup", default="E:/desktop/LUMIX/lumix_ml/m1_guide_backup.json")
    args = ap.parse_args()

    writes = build_guide(args.plane, args.y_top, args.y_bot, args.x_left, args.x_right)
    print(f"构建导框 {len(writes)} 个半字写 (y {args.y_top}..{args.y_bot}, x {args.x_left}..{args.x_right})")

    with LumixServiceUSB() as u:
        n_sent, mism = u.write_sparse_pixels(writes, backup_path=args.backup)
        print(f"写入完成: {n_sent} 次半字写, 回读不一致 {mism}")

    screenshot_png(args.plane, args.y_top - 20, args.y_bot - args.y_top + 40,
                   "E:/desktop/LUMIX/m1_guide_t0.png")
    print("t=0 截图已保存 m1_guide_t0.png")

    # 持久性测试：隔 3 秒再读
    time.sleep(3)
    with LumixServiceUSB() as u:
        b = u.read_mem(px_addr(args.plane, (args.y_top + args.y_bot)//2, args.x_left), 8)
    got = b[:4] == YELLOW
    print(f"t=3s 导框中部仍为黄色? {got}  (字节 {b.hex(' ')})")

    screenshot_png(args.plane, args.y_top - 20, args.y_bot - args.y_top + 40,
                   "E:/desktop/LUMIX/m1_guide_t3.png")
    print("t=3 截图已保存 m1_guide_t3.png")


if __name__ == "__main__":
    main()
