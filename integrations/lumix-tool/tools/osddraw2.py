"""Draw text into the S5 OSD plane using the verified layout.

Layout: 1024 px per half, RGB565 (2 bytes), row stride 4096 = two 1024-px
buffers side by side (double buffer).  Write the same content into both
halves so whichever buffer is displayed shows it.
"""
import argparse
import sys

sys.path.insert(0, "tools")
import s5svc as S

STRIDE = 4096
HALF = 1024

FONT = {
    "H": [0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "E": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
    "L": [0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F],
    "O": [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    " ": [0, 0, 0, 0, 0, 0, 0],
    "!": [0x04, 0x04, 0x04, 0x04, 0x04, 0x00, 0x04],
}


def draw(svc, base, text, x0, y0, scale, color):
    n = 0
    for ci, ch in enumerate(text):
        g = FONT.get(ch.upper(), FONT[" "])
        for gy in range(7):
            for gx in range(5):
                if not (g[gy] >> (4 - gx)) & 1:
                    continue
                for sy in range(scale):
                    for sx in range(scale):
                        px = x0 + (ci * 6 + gx) * scale + sx
                        py = y0 + gy * scale + sy
                        if px >= HALF:
                            continue
                        for half in (0, HALF):
                            addr = base + py * STRIDE + (px + half) * 2
                            svc.exchange_write(S.build_0x9c(addr, color))
                            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--base", type=lambda s: int(s, 0), default=0x8DC00000)
    ap.add_argument("--x", type=int, default=100)
    ap.add_argument("--y", type=int, default=100)
    ap.add_argument("--scale", type=int, default=4)
    ap.add_argument("--color", type=lambda s: int(s, 0), default=0xF800)  # red
    ap.add_argument("--delay", type=float, default=0.002)
    a = ap.parse_args()
    svc = S.Service(settle=a.delay)
    try:
        n = draw(svc, a.base, a.text, a.x, a.y, a.scale, a.color)
        print("wrote %d halfwords (%s)" % (n, a.text))
    finally:
        svc.close()


if __name__ == "__main__":
    main()
