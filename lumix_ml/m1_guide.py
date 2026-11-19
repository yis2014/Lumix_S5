"""Milestone 1: 可靠地在 OSD 平面绘制持久导框（写后读回校验 + 失败定点重试）。

已验证的事实：
  - OSD Plane A = 0x8DC00000, 行跨度 4096B, 1024px 宽, 像素序 [A,B,G,R]
  - 相机静止待机时 OSD 不被整帧重绘，写进去的像素稳定持久（30s+ 实测）
  - 0x9c 写入有 ~5-8% 偶发丢命令，须读回校验 + 定点重试

用法：
  python m1_guide.py draw         # 画 2.39:1 导框
  python m1_guide.py clear        # 清除导框（把黄色区域恢复为零）
  python m1_guide.py shot         # 截图当前 OSD
"""
import argparse
import time

from osd_tool import write_png_rgba
from usb_link import LumixServiceUSB

PLANE_A = 0x8DC00000
STRIDE = 4096
WIDTH = 1024

# 黄色 [A,B,G,R] = [FF,00,DC,FF]
YELLOW = bytes((0xFF, 0x00, 0xDC, 0xFF))
ZERO = bytes((0, 0, 0, 0))

# 2.39:1 导框（在 1024x640 有效画布内）
Y_TOP, Y_BOT = 280, 400
X_LEFT, X_RIGHT = 100, 924


def px(base, y, x):
    return base + y * STRIDE + x * 4


def gen_box_pixels(y_top, y_bot, x_left, x_right):
    """生成导框的所有像素地址列表（每个像素 4 字节）。"""
    addrs = set()
    for x in range(x_left, x_right):
        for t in (0, 1):
            for y in (y_top + t, y_bot + t):
                addrs.add(px(PLANE_A, y, x))
    for y in range(y_top, y_bot + 2):
        for t in (0, 1):
            for x in (x_left + t, x_right - 1 + t):
                addrs.add(px(PLANE_A, y, x))
    return sorted(addrs)


def write_pixels_reliable(u, addrs, color, rounds=6):
    """逐半字「写→读回验证→失败重试」，0x9c 写入必须靠读回同步，否则批量连写会丢命令。

    实测结论：
      - 单点写+读回：100% 可靠
      - 连续批量写（不打读回）：~85% 命令丢失
      - 写后立即读回该半字，失败重试一次即可达 100%
    """
    lo = color[0:2]
    hi = color[2:4]
    lo_v = int.from_bytes(lo, "little")
    hi_v = int.from_bytes(hi, "little")
    pending = list(addrs)
    for rnd in range(rounds):
        still_bad = []
        for a in pending:
            for off, val, want in ((0, lo_v, lo), (2, hi_v, hi)):
                for attempt in range(2):  # 最多写 2 次
                    try:
                        u.write_u16(a + off, val, delay=0, verify=False)
                    except Exception:
                        pass
                    if u.read_mem(a + off, 2) == want:
                        break
                else:
                    still_bad.append(a)
                    break
        if not still_bad:
            return 0
        pending = still_bad
    return len(pending)


def cmd_draw():
    addrs = gen_box_pixels(Y_TOP, Y_BOT, X_LEFT, X_RIGHT)
    print(f"导框像素 {len(addrs)} 个 (y {Y_TOP}..{Y_BOT}, x {X_LEFT}..{X_RIGHT})")
    with LumixServiceUSB() as u:
        remain = write_pixels_reliable(u, addrs, YELLOW)
    print(f"完成, 残留不符 {remain} 个")
    return remain


def cmd_clear():
    addrs = gen_box_pixels(Y_TOP, Y_BOT, X_LEFT, X_RIGHT)
    with LumixServiceUSB() as u:
        remain = write_pixels_reliable(u, addrs, ZERO)
    print(f"清除完成, 残留 {remain}")


def cmd_shot(out="E:/desktop/LUMIX/m1_guide.png", y0=Y_TOP - 20, h=(Y_BOT - Y_TOP) + 40):
    with LumixServiceUSB() as u:
        raw = u.read_mem(PLANE_A + y0 * STRIDE, h * STRIDE)
    rgba = bytearray(len(raw))
    for y in range(h):
        for x in range(WIDTH):
            off = y * STRIDE + x * 4
            a, c1, c2, c3 = raw[off], raw[off+1], raw[off+2], raw[off+3]
            if a == 0:
                rgba[off:off+4] = bytes((24, 24, 24, 255))
            else:
                rgba[off:off+4] = bytes((c3, c2, c1, a))
    write_png_rgba(out, WIDTH, h, bytes(rgba))
    print(f"截图 {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["draw", "clear", "shot"])
    args = ap.parse_args()
    if args.cmd == "draw":
        cmd_draw()
    elif args.cmd == "clear":
        cmd_clear()
    else:
        cmd_shot()


if __name__ == "__main__":
    main()
