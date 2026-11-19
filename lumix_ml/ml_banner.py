"""Draw a visible LUMIX-ML banner on the DC-S5 LCD OSD plane.

Uses the exact same 0x9c RAM-write channel as the signature-bypass patch, so this is
the most direct on-camera demonstration that we control the main core's memory.

  python ml_banner.py draw    # draw banner + 2.39:1 frame, then save a verification PNG
  python ml_banner.py shot    # only capture the current OSD region to PNG
  python ml_banner.py clear   # restore the original pixels from the JSON backup

OSD plane A = 0x8DC00000, stride 4096, 1024 px wide, pixel order [A,B,G,R].
Nothing is written to NAND; `clear` or a reboot removes the overlay.
"""
import sys
import time

from osd_tool import FONT_5X7, write_png_rgba
from usb_link import LumixServiceUSB

PLANE_A = 0x8DC00000
PLANE_B = 0x8DF00000
# optional second CLI argument: A (default) or B -> which OSD plane to draw on
PLANE_SEL = (sys.argv[2].upper() if len(sys.argv) > 2 else "A")
PLANE_BASE = PLANE_B if PLANE_SEL == "B" else PLANE_A
STRIDE = 4096
WIDTH = 1024
BACKUP = rf"E:\desktop\LUMIX\ml_banner_backup_{PLANE_SEL}.json"
SHOT = rf"E:\desktop\LUMIX\ml_banner_{PLANE_SEL}.png"

FONT_5X7 = dict(FONT_5X7)
FONT_5X7.update({
    "H": [0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "E": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
    "O": [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "D": [0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E],
})

TEXT = "HELLO WORLD"
SCALE = 4
TEXT_W = len(TEXT) * 6 * SCALE - SCALE
TEXT_H = 7 * SCALE
# Measured plane->LCD mapping (from on-camera photos):
#   the LCD shows the plane rotated 180 deg with a horizontal wrap seam near plane x=504.
#   LCD horizontal centre  <=> plane x = 1016 (seam + 512, mod 1024)
#   LCD vertical centre    <=> plane y ~ 171 (plane y=48 is near the bottom, y=306 near the top)
# Position confirmed visible on the real LCD (first successful test):
# plane x=64, y=48 -> shows up on the camera screen. The "LCD centre" estimates
# below were NOT visible on the device, so we keep the proven anchor.
X0, Y0 = 64, 48
YELLOW = (0xFF, 0x00, 0xDC, 0xFF)  # [A,B,G,R]
CYAN = (0xFF, 0xD8, 0xC0, 0x20)

# 2.39:1 guide frame inside the 1024x640 active canvas
F_TOP, F_BOT = 300, 396
F_LEFT, F_RIGHT = 120, 904

REGION_Y = 24
REGION_H = 400
DRAW_FRAME = False


def pixel_writes():
    writes = {}

    def put(x, y, color):
        x %= WIDTH  # the LCD wraps horizontally at the plane seam
        addr = PLANE_BASE + y * STRIDE + x * 4
        writes[addr] = color[0] | (color[1] << 8)
        writes[addr + 2] = color[2] | (color[3] << 8)

    cx = X0
    for ch in TEXT:
        glyph = FONT_5X7.get(ch, FONT_5X7[" "])
        for gy in range(7):
            bits = glyph[gy]
            for gx in range(5):
                if (bits >> (4 - gx)) & 1:
                    for sy in range(SCALE):
                        for sx in range(SCALE):
                            put(cx + gx * SCALE + sx, Y0 + gy * SCALE + sy, YELLOW)
        cx += 6 * SCALE

    # underline below the banner
    for x in range(X0, cx - SCALE):
        for t in range(2):
            put(x, Y0 + 7 * SCALE + 4 + t, CYAN)

    # amber 2.39:1 frame (optional: disabled for the plain HELLO WORLD banner)
    if DRAW_FRAME:
        for x in range(F_LEFT, F_RIGHT):
            for t in (0, 1):
                put(x, F_TOP + t, YELLOW)
                put(x, F_BOT + t, YELLOW)
        for y in range(F_TOP, F_BOT + 2):
            for t in (0, 1):
                put(F_LEFT + t, y, YELLOW)
                put(F_RIGHT - 1 + t, y, YELLOW)
    return writes


def capture(u, out=SHOT):
    raw = u.read_mem(PLANE_BASE + REGION_Y * STRIDE, REGION_H * STRIDE)
    rgba = bytearray(len(raw))
    for y in range(REGION_H):
        for x in range(WIDTH):
            off = y * STRIDE + x * 4
            a, c1, c2, c3 = raw[off:off + 4]
            if a == 0:
                bg = 20 if ((x // 32 + y // 32) & 1) == 0 else 28
                rgba[off:off + 4] = bytes((bg, bg, bg, 255))
            else:
                rgba[off:off + 4] = bytes((c3, c2, c1, 255))
    write_png_rgba(out, WIDTH, REGION_H, bytes(rgba))
    print(f"verification PNG: {out}")


def draw():
    import json
    import os
    writes = pixel_writes()
    print(f"pixels to set: {len(writes)} halfwords")
    t0 = time.time()
    with LumixServiceUSB() as u:
        # 1) block-level backup: keep pristine originals, add any newly touched blocks
        blocks = sorted({a & ~0x3FF for a in writes})
        existing = {"blocks": []}
        if os.path.exists(BACKUP):
            with open(BACKUP, "r", encoding="utf-8") as f:
                existing = json.load(f)
        have = {int(r["block_addr"], 16) for r in existing["blocks"]}
        added = 0
        for b in blocks:
            if b not in have:
                existing["blocks"].append({"block_addr": hex(b), "orig_hex": u.read_block(b).hex()})
                added += 1
        if added or not os.path.exists(BACKUP):
            existing["timestamp"] = time.time()
            with open(BACKUP, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
        print(f"backup blocks: {len(existing['blocks'])} ({added} newly added)")

        # 2) reliable per-halfword write with immediate readback and retries
        pending = sorted(writes)
        for rnd in range(1, 9):
            bad = []
            for a in pending:
                val = writes[a]
                for _ in range(3):
                    try:
                        u.write_u16(a, val, delay=0, verify=False)
                        if int.from_bytes(u.read_mem(a, 2), "little") == val:
                            break
                    except Exception:
                        time.sleep(0.002)
                else:
                    bad.append(a)
            print(f"round {rnd}: remaining {len(bad)} / {len(pending)} ({time.time()-t0:.1f}s)", flush=True)
            if not bad:
                break
            pending = bad
        capture(u)
    print("done. clear with `python ml_banner.py clear` or reboot the camera.")


def clear():
    with LumixServiceUSB() as u:
        restored = u.restore_sparse_backup(BACKUP, delay=0.0)
        print(f"restored {restored} halfwords")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "draw"
    if cmd == "draw":
        draw()
    elif cmd == "clear":
        clear()
    elif cmd == "shot":
        with LumixServiceUSB() as u:
            capture(u)
    else:
        raise SystemExit("usage: ml_banner.py [draw|shot|clear]")
