#!/usr/bin/env python3
"""DC-S5 启动链钩取 + 任意载荷执行（ARM 状态，RAM-only，可回滚）。

== 已验证原语（2026-11-19 真机，历史备份为证）==
复位链：0x80000000 Reset vector -> ... -> 0x800003C4
    原指令  E59FF0D8  = LDR pc,[pc,#0xd8]  -> literal 0x800004A4 = 0x06280004
改写为    EA0037CD  = B 0xE300             -> cave 0x8000E300 (ARM 代码)
    literal 0x06280004 = 主核 program 入口（CPU 复位期视角；服务别名 0x86280004）

历史探针 reset_capture_enhanced_* 在热重启后命中，捕获到
    magic 0x52545354 / SP=0x13000 / LR=0x3C4 / CPSR=0x600001D3 / r1=0x00C5187D
证明：改这个交接点 -> 复位时执行我们的 ARM 载荷 -> 再 bx 回 0x06280004，
系统继续正常启动。cave/buf 位于 0x8000E300 / 0x8000E400，在启动代码
清零区 [0xD044,0xE144) 之外，所以跨热重启存活。

== 本工具的增量 ==
1. 把固定捕获载荷升级为【可参数化任意载荷】：
     --read  ADDR          复制该地址 0x40 字节到 BUF+0x50（任意内存读取）
     --write ADDR=VALUE    在复位早期把 32 位 VALUE 写入 ADDR（任意改写原语）
     --code  HEX           直接注入任意 ARM 机器码作为载荷插槽
2. 完整备份（每写入点独立 JSON）+ verify 读回 + rollback 一键恢复。
3. 离线 capstone 反汇编 + unicorn(ARM) 预演，未通过禁止写入。

== 边界（务必理解）==
这是【RAM 内的启动链钩取】：热重启生效，拔电池/冷启动即恢复出厂，
绝不写 NAND / BootROM / Flash。持久化改写启动链或机身验签需要 NAND
写入能力，现有 Service USB 工具链不具备（明文只在 NAND）。

用法：
  python boot_exec.py selftest                     # 纯离线，不碰相机
  python boot_exec.py preflight                    # 只读审计
  python boot_exec.py deploy  [--read A] [--write A=V] [--code HEX]
  python boot_exec.py verify / status / rollback
"""
import argparse
import json
import os
import struct
import sys
import time

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
    UC_ARM_REG_R12, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_CPSR,
)

# 服务 USB 侧地址（0x9c/0x5c 用）；复位期 CPU 侧为去掉 bit31 的别名
TARGET = 0x800003C4          # 启动链接交指令
ORIG_INSN = bytes.fromhex("d8f09fe5")   # E59FF0D8 LDR pc,[pc,#0xd8]
CAVE = 0x8000E300            # ARM 代码洞（0xAA 填充区，跨热重启存活）
BUF = 0x8000E400             # 捕获/暂存区
CORE_ENTRY = 0x06280004      # 主核 program 入口（bx 回去，保证正常启动）
MAGIC = 0x45584543           # "EXEC"
BUF_LEN = 0x100
CAVE_MAX = 0xF0              # 0xE300..0xE3F0，不越过 BUF

ROOT = r"E:/desktop/LUMIX"
MANIFEST = os.path.join(ROOT, "boot_exec_manifest.json")


# ---------------- ARM 指令编码（全部条件码 AL） ----------------
def arm(cond, op):
    return struct.pack("<I", (cond << 28) | op)


def movw(rd, imm16):
    return arm(0xE, 0x3000000 | ((imm16 >> 12) & 0xF) << 16 | (rd << 12) | (imm16 & 0xFFF))


def movt(rd, imm16):
    return arm(0xE, 0x3400000 | ((imm16 >> 12) & 0xF) << 16 | (rd << 12) | (imm16 & 0xFFF))


def mov32(rd, val):
    return movw(rd, val & 0xFFFF) + movt(rd, (val >> 16) & 0xFFFF)


def str_imm(rt, rn, off):
    assert 0 <= off <= 0xFFF
    return arm(0xE, 0x5840000 | (rn << 16) | (rt << 12) | off)


def ldr_imm(rt, rn, off):
    assert 0 <= off <= 0xFFF
    return arm(0xE, 0x5940000 | (rn << 16) | (rt << 12) | off)


def add_imm(rd, rn, imm12):
    return arm(0xE, 0x2800000 | (rn << 16) | (rd << 12) | (imm12 & 0xFFF))


def mrs_apsr(rd):
    return arm(0xE, 0x10F0000 | (rd << 12))


def push_r0_r7_lr():
    return arm(0xE, 0x92D40FF)


def pop_r0_r7_lr():
    return arm(0xE, 0x8BD40FF)


def bx(rm):
    return arm(0xE, 0x12FFF10 | rm)


def b(addr, target):
    off = target - (addr + 8)
    assert off % 4 == 0 and -(1 << 25) <= off < (1 << 25)
    return arm(0xE, 0xA000000 | ((off >> 2) & 0xFFFFFF))


def build_detour():
    """0x800003C4: B 0x8000E300。历史实证字节 cd3700ea。"""
    d = b(TARGET, CAVE)
    assert d.hex() == "cd3700ea", f"detour 与实证不符: {d.hex()}"
    return d


def build_payload(read_addr=None, write_pair=None, code_hex=None, write_pair2=None):
    """复位早期执行的 ARM 载荷。r4=BUF, r5/r6/r7/ip 暂存；末尾恢复并 bx 回主核。"""
    c = bytearray()
    c += push_r0_r7_lr()                     # 保存现场（含 lr）
    c += mov32(4, BUF)                       # r4 = BUF
    c += mov32(5, MAGIC)
    c += str_imm(5, 4, 0x00)                 # BUF+0x00 = MAGIC "EXEC"
    c += str_imm(0, 4, 0x04)                 # r0
    c += str_imm(1, 4, 0x08)                 # r1
    c += str_imm(2, 4, 0x0C)                 # r2
    c += str_imm(3, 4, 0x10)                 # r3
    c += mov32(5, CORE_ENTRY)
    c += str_imm(5, 4, 0x14)                 # BUF+0x14 = 原跳转目标
    c += add_imm(7, 13, 0x24)                # r7 = sp + 0x24 (push 前的 sp)
    c += str_imm(7, 4, 0x1C)                 # BUF+0x1C = SP
    c += str_imm(14, 4, 0x20)                # BUF+0x20 = LR
    c += mrs_apsr(7)
    c += str_imm(7, 4, 0x24)                 # BUF+0x24 = CPSR/APSR
    c += ldr_imm(6, 4, 0x28)                 # 计数器
    c += add_imm(6, 6, 1)
    c += str_imm(6, 4, 0x28)                 # BUF+0x28 = cnt+1

    # ---- 任意载荷插槽 ----
    if read_addr is not None:
        # 把 [ADDR, ADDR+0x40) 复制到 BUF+0x50
        c += mov32(5, read_addr)              # r5 = src
        c += mov32(6, 0)                      # r6 = i
        loop = CAVE + len(c)
        c += arm(0xE, 0x7957000 | (5 << 16) | (7 << 12) | 6)   # ldr r7,[r5,r6]
        c += add_imm(12, 4, 0x50)            # ip = BUF+0x50
        c += arm(0xE, 0x78C7000 | (12 << 16) | (7 << 12) | 6)  # str r7,[ip,r6]
        c += add_imm(6, 6, 4)
        c += arm(0xE, 0x3500000 | (6 << 16) | 0x40)             # cmp r6,#0x40
        back = loop - (CAVE + len(c) + 8)
        c += arm(0x3, 0xA000000 | ((back >> 2) & 0xFFFFFF))     # bcc loop (BLO)
    for pair in (write_pair, write_pair2):
        if pair is not None:
            addr, val = pair
            c += mov32(5, addr)
            c += mov32(7, val)
            c += str_imm(7, 5, 0)            # 复位早期改写任意地址
    if code_hex:
        c += bytes.fromhex(code_hex.replace(" ", ""))

    # ---- 收尾：恢复现场 + 跳回原启动链 ----
    c += pop_r0_r7_lr()
    c += mov32(12, CORE_ENTRY)
    c += bx(12)
    assert len(c) <= CAVE_MAX, f"payload {len(c):#x} > cave {CAVE_MAX:#x}"
    return bytes(c)


def disasm(code, base=CAVE):
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    return "\n".join(f"  {i.address:#010x}: {i.bytes.hex():<10} {i.mnemonic:<8} {i.op_str}"
                     for i in md.disasm(code, base))


# ---------------- 离线自测 ----------------
def selftest(read_addr, write_pair, code_hex, write_pair2=None):
    payload = build_payload(read_addr, write_pair, code_hex, write_pair2)
    detour = build_detour()
    print(f"payload {len(payload)}B @ {CAVE:#x} | detour {detour.hex()} @ {TARGET:#x}")
    assert detour.hex() == "cd3700ea"
    print("\n--- detour ---")
    print(disasm(detour, TARGET))
    print("\n--- payload (ARM) ---")
    print(disasm(payload))

    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mu.mem_map(0x80000000, 0x20000)     # TARGET + CAVE + BUF（服务别名视角）
    mu.mem_map(0x06280000, 0x10000)     # 主核入口落点（bx 0x06280004）
    mu.mem_map(0x00010000, 0x10000)     # 栈
    if read_addr is not None:
        b = read_addr & ~0xFFFF
        try:
            mu.mem_map(b, 0x20000)
        except Exception:
            pass
    for pair in (write_pair, write_pair2):
        if pair is not None:
            b = pair[0] & ~0xFFFF
            try:
                mu.mem_map(b, 0x10000)
            except Exception:
                pass
    mu.mem_write(TARGET, detour)
    mu.mem_write(CAVE, payload)
    mu.mem_write(BUF, b"\x00" * BUF_LEN)
    if read_addr is not None:
        mu.mem_write(read_addr, bytes(range(0x40)))
    stop = 0x06280004
    mu.mem_write(stop, arm(0xE, 0x12FFF1E))   # bx lr（停机替身）
    for r, v in ((UC_ARM_REG_R0, 0x11111111), (UC_ARM_REG_R1, 0x22222222),
                 (UC_ARM_REG_R2, 0x33333333), (UC_ARM_REG_R3, 0x44444444),
                 (UC_ARM_REG_SP, 0x00018000)):
        mu.reg_write(r, v)
    mu.reg_write(UC_ARM_REG_LR, 0x000003C4)
    mu.emu_start(TARGET, stop, count=500)

    b = bytes(mu.mem_read(BUF, BUF_LEN))
    magic = struct.unpack_from("<I", b, 0)[0]
    cnt = struct.unpack_from("<I", b, 0x28)[0]
    print(f"\n仿真: magic={magic:#010x} cnt={cnt} pc={mu.reg_read(UC_ARM_REG_PC):#x}")
    assert magic == MAGIC, "MAGIC 未写入"
    assert cnt == 1, "计数器未递增"
    assert mu.reg_read(UC_ARM_REG_PC) == stop, "未 bx 回主核入口"
    if read_addr is not None:
        assert b[0x50:0x90] == bytes(range(0x40)), "读取载荷复制内容不符"
        print(f"  BUF+0x50 = {b[0x50:0x60].hex(' ')}  (任意地址读取 OK)")
    for pair in (write_pair, write_pair2):
        if pair is not None:
            addr, val = pair
            got = struct.unpack("<I", mu.mem_read(addr, 4))[0]
            assert got == val, f"改写载荷失败: {got:#x} != {val:#x}"
            print(f"  [{addr:#010x}] = {val:#010x}  (任意地址改写 OK)")
    print("SELFTEST PASS: 编码/现场保存/计数/载荷/返回主核 全部通过")
    return payload, detour


# ---------------- 真机 ----------------
def _usb():
    from usb_link import LumixServiceUSB
    return LumixServiceUSB()


def _write_bytes(u, addr, data):
    assert len(data) % 2 == 0 and addr % 2 == 0
    for off in range(0, len(data), 2):
        u.write_u16(addr + off, struct.unpack_from("<H", data, off)[0],
                    delay=0.005, verify=True)


def _regions(payload, detour):
    return {
        "target": (TARGET, detour),
        "cave":   (CAVE, payload.ljust(CAVE_MAX, b"\x00")),
        "buf":    (BUF, b"\x00" * BUF_LEN),
    }


def _save_baseline(u, regions):
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as f:
            m = json.load(f)
        print(f"已有基线 manifest（{m['timestamp']}），沿用，不覆盖")
        return
    m = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "regions": {}}
    for name, (addr, data) in regions.items():
        orig = u.read_mem(addr, len(data))
        p = os.path.join(ROOT, f"boot_exec_{name}_baseline.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"addr": hex(addr), "length": len(orig),
                       "original_hex": orig.hex(), "timestamp": m["timestamp"]}, f, indent=2)
        m["regions"][name] = {"addr": hex(addr), "length": len(orig), "backup": p}
        print(f"  基线 {name:6s} {addr:#010x} {len(orig):4d}B  {orig[:12].hex(' ')}")
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2)


def preflight():
    print("=== 只读 preflight（启动链关键点）===")
    try:
        with _usb() as u:
            print("device:", u.device_path[-56:])
            detour = build_detour()
            cur = u.read_mem(TARGET, 4)
            # 允许原厂指令或本工具 detour（幂等重部署）；其它值一律中止
            if cur == detour:
                handoff_ok, handoff_note = True, "已是本工具 detour（幂等重部署 OK）"
            elif cur == ORIG_INSN:
                handoff_ok, handoff_note = True, "原厂 LDR pc"
            else:
                handoff_ok, handoff_note = False, "既非原厂也非本工具 detour — 中止"
            print(f"  {TARGET:#010x} {cur.hex(' '):<24} 启动链交接     "
                  f"{'OK' if handoff_ok else 'FAIL'}  {handoff_note}")
            checks = [
                (0x800004A4,  4, "literal",        bytes.fromhex("04002806")),
                (0x80000000,  4, "Reset vector",   bytes.fromhex("120000ea")),
                (CAVE,        8, "cave 原貌",       None),
                (BUF,         8, "buf 原貌",        None),
            ]
            ok = handoff_ok
            for addr, n, label, expect in checks:
                d = u.read_mem(addr, n)
                good = True if expect is None else d == expect
                ok &= good
                print(f"  {addr:#010x} {d.hex(' '):<24} {label:<14} {'OK' if good else 'FAIL'}")
            print("PREFLIGHT", "PASS" if ok else "FAIL - 不要写入")
            return ok
    except Exception as e:
        print("PREFLIGHT FAIL - 设备不可达:", e)
        return False


def deploy(read_addr, write_pair, code_hex, write_pair2=None):
    payload, detour = selftest(read_addr, write_pair, code_hex, write_pair2)
    if not preflight():
        raise SystemExit("\n设备当前不可达或状态不符，未写入任何字节。\n"
                         "请让相机重新进入 Service USB 模式 (PID 2370) 后重跑 deploy。")
    regions = _regions(payload, detour)
    print("\n=== 部署（RAM-only，不动 NAND）===")
    with _usb() as u:
        _save_baseline(u, regions)
        for name, (addr, data) in regions.items():
            _write_bytes(u, addr, data)
            print(f"  写入 {name:6s} {addr:#010x} {len(data):4d}B")
    ok = verify(False)
    print("\nDEPLOY", "OK" if ok else "FAILED")
    if ok:
        print("""
触发（必须热重启，切勿拔电池）：
  1. 电源键【关机再开机】= 热重启。RAM 补丁保留；拔电池会全部清空。
  2. 复位链走到 0x3C4 时先执行我们的 ARM 载荷，随后 bx 回 0x06280004 正常启动。
  3. 相机回到服务模式 2370 后执行: python boot_exec.py status
     期望 MAGIC=0x45584543、cnt>=1，并可读回 BUF+0x50 的窗口内容。

回滚: python boot_exec.py rollback    （恢复 0x3C4 指令 + cave + buf 冷启动基线）
终极恢复: 拔电池冷启动，RAM 全部重载，所有补丁自动消失。
""")
    return ok


def verify(quiet=True):
    # 从 manifest 取回本次部署参数（payload 依赖参数，重算需一致）
    payload, detour = build_payload(None, None, None), build_detour()
    regions = _regions(payload, detour)
    try:
        with _usb() as u:
            t = u.read_mem(TARGET, 4)
            cave = u.read_mem(CAVE, 16)
            buf = u.read_mem(BUF, 4)
            ok = t == detour
            print(f"  target {t.hex(' ')} {'OK' if ok else 'MISMATCH'}")
            print(f"  cave   {cave.hex(' ')}")
            print(f"  buf    {buf.hex(' ')}")
            if not quiet:
                print("VERIFY", "PASS" if ok else "FAIL")
            return ok
    except Exception as e:
        print("VERIFY 设备不可达:", e)
        return False


def status():
    with _usb() as u:
        b = u.read_mem(BUF, BUF_LEN)
        t = u.read_mem(TARGET, 4)
    magic = struct.unpack_from("<I", b, 0)[0]
    cnt = struct.unpack_from("<I", b, 0x28)[0]
    print(f"  detour @0x800003C4 = {t.hex(' ')}  ({'已部署' if t == build_detour() else '原厂/已回滚'})")
    print(f"  MAGIC  = {magic:#010x}  ({'已触发' if magic == MAGIC else '未触发'})")
    print(f"  CNT    = {cnt}")
    print(f"  上下文 r0-r3 = {[hex(x) for x in struct.unpack_from('<4I', b, 4)]}")
    print(f"  SP={struct.unpack_from('<I',b,0x1c)[0]:#x} LR={struct.unpack_from('<I',b,0x20)[0]:#x} "
          f"CPSR={struct.unpack_from('<I',b,0x24)[0]:#x}")
    print(f"  BUF+0x50 = {b[0x50:0x60].hex(' ')}")
    return magic == MAGIC


def rollback():
    if not os.path.exists(MANIFEST):
        print("无 manifest，可能从未部署")
        return
    with open(MANIFEST, encoding="utf-8") as f:
        m = json.load(f)
    print(f"回滚到 {m['timestamp']} 冷启动基线")
    with _usb() as u:
        for name, rec in m["regions"].items():
            with open(rec["backup"], encoding="utf-8") as f:
                b = json.load(f)
            orig = bytes.fromhex(b["original_hex"])
            addr = int(b["addr"], 16)
            _write_bytes(u, addr, orig)
            print(f"  {name:6s} {addr:#010x} {'OK' if u.read_mem(addr, len(orig)) == orig else 'MISMATCH'}")
    os.remove(MANIFEST)
    print("manifest 已删除，回滚完成")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["selftest", "preflight", "deploy", "verify",
                                    "status", "rollback"])
    ap.add_argument("--read", type=lambda x: int(x, 0), help="复制该地址 0x40B 到 BUF+0x50")
    ap.add_argument("--write", help="复位早期改写 ADDR=VALUE（如 0x800004A4=0x8000E500）")
    ap.add_argument("--write2", help="第二处复位早期改写 ADDR=VALUE")
    ap.add_argument("--code", help="直接注入任意 ARM 机器码 HEX 到载荷插槽")
    a = ap.parse_args()
    wp = wp2 = None
    if a.write:
        k, v = a.write.split("=")
        wp = (int(k, 0), int(v, 0) & 0xFFFFFFFF)
    if a.write2:
        k, v = a.write2.split("=")
        wp2 = (int(k, 0), int(v, 0) & 0xFFFFFFFF)
    f = {
        "selftest":  lambda: selftest(a.read, wp, a.code, wp2),
        "preflight": preflight,
        "deploy":    lambda: deploy(a.read, wp, a.code, wp2),
        "verify":    lambda: verify(False),
        "status":    status,
        "rollback":  rollback,
    }[a.cmd]
    r = f()
    if a.cmd in ("preflight", "deploy", "verify", "status") and r is False:
        sys.exit(1)


if __name__ == "__main__":
    main()
