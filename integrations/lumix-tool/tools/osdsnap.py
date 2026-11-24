"""Grab the S5 OSD plane over the service USB and save it as a PNG.

OSD format (verified by the reference project): 1024 px wide, 32-bit pixels,
row stride 4096, byte order [A, B, G, R], double-buffered planes at
0x8DC00000 and 0x8DF00000.
"""
import argparse
import sys

from PIL import Image

sys.path.insert(0, "tools")
import s5svc as S

STRIDE = 4096
WIDTH = 1024


def grab(base, height):
    svc = S.Service(settle=0.001)
    try:
        total = height * STRIDE
        buf = bytearray()
        for off in range(0, total, 1024):
            addr = base + off
            r = svc.exchange(S.build_0x5c(addr))
            if len(r) != 1030 or r[3] != 5:
                raise RuntimeError("read failed at 0x%X" % addr)
            buf += r[4:1028]
    finally:
        svc.close()
    return bytes(buf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--base", type=lambda s: int(s, 0), default=0x8DC00000)
    ap.add_argument("--height", type=int, default=720)
    a = ap.parse_args()

    raw = grab(a.base, a.height)
    rows = a.height * STRIDE
    raw = raw[:rows]
    img = Image.new("RGBA", (WIDTH, a.height))
    px = img.load()
    nonzero = 0
    for y in range(a.height):
        ro = y * STRIDE
        for x in range(WIDTH):
            o = ro + x * 4
            al, b, g, r = raw[o], raw[o + 1], raw[o + 2], raw[o + 3]
            if al or b or g or r:
                nonzero += 1
            if al == 0:
                bg = 22 if ((x // 32 + y // 32) & 1) == 0 else 28
                px[x, y] = (bg, bg + 2, bg + 4, 255)
            else:
                px[x, y] = (r, g, b, al)
    img.save(a.out)
    print("saved %s  base=0x%X height=%d  nonzero_px=%d" % (a.out, a.base, a.height, nonzero))


if __name__ == "__main__":
    main()
