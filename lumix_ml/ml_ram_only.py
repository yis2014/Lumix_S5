"""RAM-only LUMIX ML banner and 2.39:1 composition guide for the DC-S5.

Reuses ml_banner's verified per-halfword write/readback engine and the proven
Plane A anchor, but keeps independent backup/PNG files so the earlier HELLO
WORLD artifacts are never overwritten.

  python ml_ram_only.py draw A
  python ml_ram_only.py shot A
  python ml_ram_only.py clear A

No NAND writes.  Clear restores pixels; a power cycle also removes the overlay.
"""
import sys

import ml_banner as m

m.TEXT = "LUMIX ML"
m.DRAW_FRAME = True
TAG = f"_{sys.argv[3].lower()}" if len(sys.argv) > 3 else ""
m.BACKUP = rf"E:\desktop\LUMIX\ml_ram_only{TAG}_backup_{m.PLANE_SEL}.json"
SHOT = rf"E:\desktop\LUMIX\ml_ram_only{TAG}_{m.PLANE_SEL}.png"

# ml_banner.capture captured its default argument when defined.  Wrap it so
# draw() writes this feature's own PNG rather than ml_banner_A.png.
_verified_capture = m.capture
m.capture = lambda u, out=SHOT: _verified_capture(u, out)

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "draw"
    if cmd == "draw":
        m.draw()
    elif cmd == "clear":
        m.clear()
    elif cmd == "shot":
        with m.LumixServiceUSB() as u:
            m.capture(u)
    else:
        raise SystemExit("usage: ml_ram_only.py [draw|shot|clear] [A|B]")
