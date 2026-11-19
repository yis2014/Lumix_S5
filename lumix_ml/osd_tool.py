"""LUMIX-ML Live OSD Framebuffer Screenshot & Overlay Renderer for Panasonic DC-S5.

Verified OSD Hardware Format (Milestone 1):
  - Double-buffered 32-bit OSD planes spaced by 0x00300000 (3 MiB):
      Plane A: 0x8DC00000 .. 0x8DD80000
      Plane B: 0x8DF00000 .. 0x8E010000
  - Row Stride: 4096 bytes (1024 pixels * 4 bytes/pixel)
  - Active LCD Viewport: ~720x480 or 960x640 inside 1024-px pitch
  - Pixel Byte Order: [Alpha, Ch1, Ch2, Ch3] (byte 0 = Alpha: 0x00 transparent, 0xFF opaque)
"""
import argparse
import os
import struct
import sys
import time
import zlib

from usb_link import LumixServiceUSB

PLANE_A = 0x8DC00000
PLANE_B = 0x8DF00000
STRIDE = 4096  # 1024 px * 4 bytes


def write_png_rgba(path: str, width: int, height: int, rgba_bytes: bytes):
    """Pure-Python PNG writer (no Pillow dependency)."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    raw_rows = bytearray()
    row_bytes = width * 4
    for y in range(height):
        raw_rows.append(0)  # Filter type 0 (None)
        off = y * row_bytes
        raw_rows += rgba_bytes[off : off + row_bytes]

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw_rows), 6))
        + chunk(b"IEND", b"")
    )
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)


# Minimal crisp 5x7 bitmap font for "LUMIX-ML v0.1  2.39:1"
FONT_5X7 = {
    " ": [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
    "-": [0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00],
    ".": [0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C],
    ":": [0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x00],
    "0": [0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E],
    "1": [0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "2": [0x0E, 0x11, 0x01, 0x06, 0x08, 0x10, 0x1F],
    "3": [0x1F, 0x02, 0x04, 0x06, 0x01, 0x11, 0x0E],
    "9": [0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C],
    "I": [0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "L": [0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F],
    "M": [0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11],
    "U": [0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "X": [0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11],
    "v": [0x00, 0x00, 0x11, 0x11, 0x11, 0x0A, 0x04],
    "R": [0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11],
    "A": [0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "W": [0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11],
}


def render_text_to_canvas(canvas, cw, ch, x0, y0, text, scale, fg_argb, bg_argb=None):
    """Render scaled 5x7 bitmap text onto a local (cw x ch) pixel array of 4-byte pixels."""
    if bg_argb is not None:
        pad = 4
        total_w = len(text) * 6 * scale + pad * 2
        total_h = 7 * scale + pad * 2
        for yy in range(max(0, y0 - pad), min(ch, y0 - pad + total_h)):
            for xx in range(max(0, x0 - pad), min(cw, x0 - pad + total_w)):
                canvas[(yy * cw + xx) * 4 : (yy * cw + xx + 1) * 4] = bg_argb

    cx = x0
    for ch_char in text:
        glyph = FONT_5X7.get(ch_char, FONT_5X7[" "])
        for gy in range(7):
            row_bits = glyph[gy]
            for gx in range(5):
                if (row_bits >> (4 - gx)) & 1:
                    for sy in range(scale):
                        for sx in range(scale):
                            px = cx + gx * scale + sx
                            py = y0 + gy * scale + sy
                            if 0 <= px < cw and 0 <= py < ch:
                                canvas[(py * cw + px) * 4 : (py * cw + px + 1) * 4] = fg_argb
        cx += 6 * scale


def cmd_screenshot(out_png: str, base_addr: int, height: int):
    t0 = time.time()
    size = height * STRIDE
    with LumixServiceUSB() as usb:
        raw = usb.read_mem(base_addr, size)

    # Convert camera [A, B, G, R] or [A, R, G, B] to standard PNG [R, G, B, A]
    # Also composite over dark checker/charcoal where A == 0 so UI elements are clearly visible!
    rgba = bytearray(len(raw))
    nonzero_rows = []
    for y in range(height):
        row_nz = False
        for x in range(1024):
            off = y * STRIDE + x * 4
            a, c1, c2, c3 = raw[off], raw[off + 1], raw[off + 2], raw[off + 3]
            if a != 0 or c1 != 0 or c2 != 0 or c3 != 0:
                row_nz = True
            if a == 0:
                # Subtle dark grid background so transparent areas are distinguishable
                bg = 26 if ((x // 16 + y // 16) & 1) == 0 else 32
                rgba[off : off + 4] = bytes((bg, bg, bg, 255))
            else:
                # Assume [A, B, G, R] -> R=c3, G=c2, B=c1, A=a
                rgba[off : off + 4] = bytes((c3, c2, c1, a))
        if row_nz:
            nonzero_rows.append(y)

    write_png_rgba(out_png, 1024, height, bytes(rgba))
    y_min = min(nonzero_rows) if nonzero_rows else -1
    y_max = max(nonzero_rows) if nonzero_rows else -1
    print(
        f"Saved screenshot {out_png} (1024x{height} from {base_addr:#010x}) in {time.time()-t0:.2f}s | "
        f"active UI rows: {y_min}..{y_max} ({len(nonzero_rows)} non-empty rows)"
    )


def decode_osd(raw: bytes, height: int):
    """Decode camera [A,B,G,R] pixels and composite over a dark host-side canvas."""
    rgba = bytearray(len(raw))
    for y in range(height):
        for x in range(1024):
            off = y * STRIDE + x * 4
            a, b, g, r = raw[off : off + 4]
            if a == 0:
                bg = 22 if ((x // 32 + y // 32) & 1) == 0 else 28
                rgba[off : off + 4] = bytes((bg, bg + 2, bg + 4, 255))
            else:
                # Alpha-composite the native OSD over the host background.
                bg = 22 if ((x // 32 + y // 32) & 1) == 0 else 28
                inv = 255 - a
                rgba[off : off + 4] = bytes(
                    (
                        (r * a + bg * inv) // 255,
                        (g * a + (bg + 2) * inv) // 255,
                        (b * a + (bg + 4) * inv) // 255,
                        255,
                    )
                )
    return bytes(rgba)


def cmd_preview(out_png: str, raw_in: str, raw_out: str, clean_out: str,
                base_addr: int, height: int, aspect: float, live: bool):
    """Render Magic-Lantern-style guides on the host; never writes camera memory."""
    from PIL import Image, ImageDraw, ImageFont

    if live:
        size = height * STRIDE
        with LumixServiceUSB() as usb:
            raw = usb.read_mem(base_addr, size)
        if raw_out:
            with open(raw_out, "wb") as f:
                f.write(raw)
    else:
        with open(raw_in, "rb") as f:
            raw = f.read()
        expected = height * STRIDE
        if len(raw) != expected:
            raise ValueError(f"raw frame must be {expected} bytes, got {len(raw)}")

    clean = Image.frombytes("RGBA", (1024, height), decode_osd(raw, height))
    if clean_out:
        clean.save(clean_out)

    # A slightly wider canvas leaves room for a status header without hiding the OSD.
    header = 54
    image = Image.new("RGBA", (1024, height + header), (12, 17, 24, 255))
    image.paste(clean, (0, header))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 20)
        small = ImageFont.truetype("arial.ttf", 15)
    except OSError:
        font = small = ImageFont.load_default()

    draw.text((22, 15), "LUMIX-ML  /  READ-ONLY HOST PREVIEW", font=font,
              fill=(105, 225, 210, 255))
    label = f"DC-S5  |  {aspect:.2f}:1  |  OSD {base_addr:#010x}"
    draw.text((690, 19), label, font=small, fill=(157, 171, 188, 255))

    # Center the requested aspect-ratio frame inside the 1024-wide OSD canvas.
    frame_w = 944
    frame_h = int(round(frame_w / aspect))
    if frame_h > height - 48:
        frame_h = height - 48
        frame_w = int(round(frame_h * aspect))
    x0 = (1024 - frame_w) // 2
    x1 = x0 + frame_w
    y0 = header + (height - frame_h) // 2
    y1 = y0 + frame_h
    amber = (255, 214, 64, 255)
    cyan = (85, 205, 220, 210)
    white = (235, 241, 245, 220)

    # Outer frame, rule-of-thirds, center cross, and 90% action-safe box.
    draw.rectangle((x0, y0, x1, y1), outline=amber, width=3)
    for i in (1, 2):
        x = x0 + frame_w * i // 3
        y = y0 + frame_h * i // 3
        draw.line((x, y0, x, y1), fill=cyan, width=1)
        draw.line((x0, y, x1, y), fill=cyan, width=1)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    draw.line((cx - 18, cy, cx + 18, cy), fill=white, width=2)
    draw.line((cx, cy - 18, cx, cy + 18), fill=white, width=2)
    sx = int(frame_w * 0.05)
    sy = int(frame_h * 0.05)
    draw.rectangle((x0 + sx, y0 + sy, x1 - sx, y1 - sy), outline=(255, 255, 255, 115), width=1)

    tag = f"ML  {aspect:.2f}:1"
    draw.rectangle((x0 + 12, y0 + 10, x0 + 154, y0 + 40), fill=(10, 15, 20, 210))
    draw.text((x0 + 21, y0 + 14), tag, font=small, fill=amber)
    draw.text((20, height + header - 25), "HOST-SIDE OVERLAY ONLY - CAMERA MEMORY UNCHANGED",
              font=small, fill=(125, 143, 158, 255))
    image.convert("RGB").save(out_png)
    print(f"Saved read-only ML preview: {out_png}")
    if raw_out and live:
        print(f"Saved raw OSD frame: {raw_out}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_shot = sub.add_parser("screenshot")
    p_shot.add_argument("out", help="Output PNG path")
    p_shot.add_argument("--base", type=lambda s: int(s, 0), default=0x8DC40000)
    p_shot.add_argument("--height", type=int, default=720)
    p_preview = sub.add_parser("preview", help="Read-only host-side Magic Lantern overlay")
    p_preview.add_argument("out", help="Output preview PNG path")
    p_preview.add_argument("--live", action="store_true", help="Capture from camera using read-only 0x5c")
    p_preview.add_argument("--raw-in", help="Offline raw OSD frame input")
    p_preview.add_argument("--raw-out", help="Save live raw OSD frame for offline reproduction")
    p_preview.add_argument("--clean-out", help="Also save clean decoded OSD PNG")
    p_preview.add_argument("--base", type=lambda s: int(s, 0), default=PLANE_A)
    p_preview.add_argument("--height", type=int, default=640)
    p_preview.add_argument("--aspect", type=float, default=2.39)
    args = ap.parse_args()

    if args.cmd == "screenshot":
        cmd_screenshot(args.out, args.base, args.height)
    elif args.cmd == "preview":
        if not args.live and not args.raw_in:
            ap.error("preview requires --live or --raw-in")
        cmd_preview(args.out, args.raw_in, args.raw_out, args.clean_out,
                    args.base, args.height, args.aspect, args.live)


if __name__ == "__main__":
    main()
