"""Render an approximate LCD-view PNG from the live OSD plane.

The DC-S5 LCD shows OSD plane A rotated 180 deg with a horizontal wrap seam near
plane x=504. This applies that mapping so we can check on-screen placement without
taking a photo of the camera.
"""
from osd_tool import write_png_rgba
from usb_link import LumixServiceUSB
import sys

PLANE_SEL = (sys.argv[1].upper() if len(sys.argv) > 1 else 'A')
PLANE_A = 0x8DF00000 if PLANE_SEL == 'B' else 0x8DC00000
STRIDE = 4096
WIDTH = 1024
Y_BASE = 0           # first plane row to include
ROWS = 360           # rows to include in the preview
SEAM = 504
OUT = rf"E:\desktop\LUMIX\ml_banner_lcd_{PLANE_SEL}.png"

with LumixServiceUSB() as u:
    raw = u.read_mem(PLANE_A + Y_BASE * STRIDE, ROWS * STRIDE)

rgba = bytearray(WIDTH * ROWS * 4)
for out_y in range(ROWS):
    plane_y = Y_BASE + out_y  # upright rows, no vertical flip
    src_row = out_y * STRIDE
    for out_x in range(WIDTH):
        plane_x = (out_x + SEAM) % WIDTH  # pure translation with wrap, no mirroring
        off = src_row + plane_x * 4
        a, c1, c2, c3 = raw[off:off + 4]
        dst = (out_y * WIDTH + out_x) * 4
        if a == 0:
            bg = 20 if ((out_x // 32 + out_y // 32) & 1) == 0 else 28
            rgba[dst:dst + 4] = bytes((bg, bg, bg, 255))
        else:
            rgba[dst:dst + 4] = bytes((c3, c2, c1, 255))

write_png_rgba(OUT, WIDTH, ROWS, bytes(rgba))
print(f"LCD-view preview: {OUT}")

