#!/usr/bin/env python3
"""DC-S5 主核：任意载荷执行 / 验签路径改写（RAM-only，全可回滚）。

背景（2026-11-19 真机审计后重写）：
  1. 代码执行原语已实证：镜头 .plf 头部校验冷函数 0x868C5E48 的 Thumb-2
     detour（deploy_validator_detour.py），计数器曾从 0 增长到 2。
  2. 旧版"功能性 payload"（build_dump_payload.py / build_nand_read_probe.py）
     把 BUF/COUNTER 放在 0x87086400 / 0x87086450，但真机读回显示那里是
     **活动浮点常量表**（6b5fbc3e 3b48c73e ...），照搬会踩坏活动数据，
     正是交接文档警告的"重启/掉线"来源。本工具改用空闲填充区。
  3. 本轮只读审计确认的可用布局：
       CAVE  0x87086300  rodata 错误消息字符串区（可执行、跨热重启存活、已实证）
       BUF   0x8F000400  纯 0x55 空闲填充（256B 中 250B 为 0x55）
       CNT   0x8F000500  纯 0x55 空闲填充
     禁用区：0x87086A00（活动浮点表 cdcccc3d）、0x90000000+（视频 DMA）、OSD 双平面。

payload 功能（真正"任意"的部分）：写 MAGIC、递增计数器、把参数化源地址 SRC
  的 8 个字（32B）复制到 BUF+8。SRC 可通过 --src 改成任意主核地址，
  因此这是可复用的"任意地址读取 + 任意代码执行"原语，而非硬编码计数器。

安全约束：
  - 只写 RAM，绝不触碰 NAND / Flash / 启动扇区。
  - 每个写入点独立 JSON 备份；rollback 恢复到部署前的冷启动基线。
  - 部署前强制 preflight；真机写入前必须通过 capstone + unicorn 离线自测。
  - 触发需相机执行镜头更新流程（冷函数），部署本身不等于已执行。

用法：
  python arb_exec.py selftest [--src 0x...]      # 纯离线，不碰相机
  python arb_exec.py preflight                   # 只读审计
  python arb_exec.py deploy   [--src 0x...]      # 部署 + 读回校验
  python arb_exec.py verify                      # 校验部署字节
  python arb_exec.py status                      # 判断是否已被触发
  python arb_exec.py rollback                    # 一键恢复
  python arb_exec.py sig-status / sig-on / sig-off   # 验签路径改写
"""
import argparse
import json
import os
import struct
import sys
import time

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP,
)

from inject_test import bw, movw_movt

# ---- 已实证地址 ----
TARGET = 0x868C5E48          # 镜头 .plf 头部/版本校验冷函数入口（Thumb-2）
ORIG = bytes.fromhex("2de9ff4f")   # push.w {r0-r11,lr}
RESUME = TARGET + 4
CAVE = 0x87086300            # 代码洞（rodata 字符串区，已实证可执行）
BUF = 0x8F000400             # 捕获缓冲（纯 0x55 空闲填充）
CNT = 0x8F000500             # 计数器（纯 0x55 空闲填充）
MAGIC = 0x45584543           # "EXEC"
# 默认复制源：启动链 literal（0x800004A4 = 0x06280004）。
# 刻意不选 0x868C5E40 —— 它与 TARGET/RESUME 仅隔 8 字节，仿真测试数据会覆盖 detour。
SRC_DEFAULT = 0x800004A4
WORDS = 8
BUF_LEN = 0x40

# ---- 验签路径（镜头 metadata ECDSA verifier）----
SIG_ADDR = 0x868C08C6
SIG_ORIG = bytes.fromhex("70b5b0b0")   # push {r4-r6,lr} ; sub sp,#0xc0
SIG_PATCH = bytes.fromhex("00207047")  # movs r0,#0 ; bx lr  -> 恒返回"有效"

ROOT = r"E:/desktop/LUMIX"
MANIFEST = os.path.join(ROOT, "arb_manifest.json")
SIG_BACKUP = os.path.join(ROOT, "arb_sig_backup.json")


# ---------------- 编码辅助 ----------------
def mm(rd, value):
    """movw/movt 对，加载 32 位立即数。"""
    return movw_movt(rd, value & 0xFFFF) + movw_movt(rd, (value >> 16) & 0xFFFF, True)


def bne_back(at, target):
    off = (target - (at + 4)) // 2
    assert -128 <= off <= 127, f"bne out of range: {off}"
    return struct.pack("<H", 0xD100 | (off & 0xFF))


def build_payload(src=SRC_DEFAULT):
    """Thumb-2 payload：MAGIC + CNT++ + 从 SRC 复制 8 个字到 BUF+8。

    只用 r0-r5；push/pop 成对，调用者寄存器全部保持；补执行被覆盖的
    原始 4 字节序言，再 b.w 回原函数体，行为 100% 保留。
    """
    c = bytearray()
    c += struct.pack("<H", 0xB43F)          # push {r0-r5}
    c += mm(4, BUF)
    c += mm(5, src)
    c += mm(2, CNT)
    c += struct.pack("<H", 0x6813)          # ldr  r3, [r2]      ; cnt
    c += struct.pack("<H", 0x3301)          # adds r3, #1
    c += struct.pack("<H", 0x6013)          # str  r3, [r2]      ; cnt++
    c += mm(3, MAGIC)
    c += struct.pack("<H", 0x6023)          # str  r3, [r4]      ; BUF[0] = MAGIC
    c += struct.pack("<H", 0x2008)          # movs r0, #8
    c += struct.pack("<H", 0x3408)          # adds r4, #8        ; r4 = BUF+8
    loop = CAVE + len(c)
    c += struct.pack("<H", 0x682B)          # ldr  r3, [r5]
    c += struct.pack("<H", 0x6023)          # str  r3, [r4]
    c += struct.pack("<H", 0x3504)          # adds r5, #4
    c += struct.pack("<H", 0x3404)          # adds r4, #4
    c += struct.pack("<H", 0x3801)          # subs r0, #1
    c += bne_back(CAVE + len(c), loop)
    c += struct.pack("<H", 0xBC3F)          # pop {r0-r5}
    c += ORIG                               # 补执行被覆盖的原始序言
    c += bw(CAVE + len(c), RESUME)          # 跳回原函数
    return bytes(c)


def build_detour():
    return bw(TARGET, CAVE)


def disasm(code, base):
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    return "\n".join(f"  {i.address:#010x}  {i.mnemonic:<8} {i.op_str}"
                     for i in md.disasm(code, base))


# ---------------- 离线自测 ----------------
def selftest(src):
    payload = build_payload(src)
    detour = build_detour()
    print(f"payload {len(payload)}B @ CAVE {CAVE:#x} | detour {detour.hex()} @ {TARGET:#x}")
    assert detour.hex() == "c0f35ab2", "detour 编码与真机实证值不符"
    assert len(payload) <= 0x50, "payload 超出 CAVE 字符串区安全范围"
    print("\n--- payload 反汇编 ---")
    print(disasm(payload, CAVE))
    print("\n--- detour 反汇编 ---")
    print(disasm(detour, TARGET))

    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    mu.mem_map(0x87086000, 0x10000)     # CAVE
    mu.mem_map(0x868C5000, 0x10000)     # TARGET + SRC
    mu.mem_map(0x8F000000, 0x10000)     # BUF / CNT
    mu.mem_map(0x80000000, 0x10000)     # stack
    # 动态映射任意 --src 源地址所在页（RAM 0x09xxxxxx 或 MMIO 0x7c00xxxx 等）
    src_page = src & ~0xFFFF
    try:
        mu.mem_map(src_page, 0x10000)
    except Exception:
        pass  # 若已映射则忽略
    mu.mem_write(CAVE, payload)
    mu.mem_write(TARGET, detour)
    mu.mem_write(RESUME, struct.pack("<H", 0x4770))   # bx lr（原函数体替身）
    mu.mem_write(BUF, b"\x55" * BUF_LEN)
    mu.mem_write(CNT, struct.pack("<I", 0))
    probe = bytes(range(0x20))
    mu.mem_write(src, probe)
    ret = 0x80001000
    mu.mem_write(ret, struct.pack("<H", 0x4770))
    regs = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
            UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5)
    vals = (0x11111111, 0x22222222, 0x33333333,
            0x44444444, 0x55555555, 0x66666666)
    for r, v in zip(regs, vals):
        mu.reg_write(r, v)
    mu.reg_write(UC_ARM_REG_LR, ret | 1)
    mu.reg_write(UC_ARM_REG_SP, 0x80008000)
    mu.reg_write(UC_ARM_REG_PC, TARGET | 1)
    mu.emu_start(TARGET | 1, ret, count=300)

    cnt = struct.unpack("<I", mu.mem_read(CNT, 4))[0]
    magic = struct.unpack("<I", mu.mem_read(BUF, 4))[0]
    copied = bytes(mu.mem_read(BUF + 8, 0x20))
    after = [mu.reg_read(r) for r in regs]
    pc = mu.reg_read(UC_ARM_REG_PC)
    print(f"\n仿真结果: cnt={cnt} magic={magic:#010x} pc={pc:#x}")
    print(f"  BUF+8 : {copied[:16].hex(' ')} ...")
    print(f"  r0-r5 : {[hex(x) for x in after]}")
    assert cnt == 1, "计数器未递增"
    assert magic == MAGIC, "MAGIC 未写入"
    assert copied == probe, "源地址复制内容不符"
    assert after == list(vals), "调用者寄存器被破坏"
    assert pc == ret, "未正确返回原函数"
    print("SELFTEST PASS: 编码/复制/计数/寄存器保持/控制流返回 全部通过")
    return payload, detour


# ---------------- 真机传输 ----------------
def _usb():
    from usb_link import LumixServiceUSB
    return LumixServiceUSB()


def _write_bytes(u, addr, data):
    assert len(data) % 2 == 0 and addr % 2 == 0
    for off in range(0, len(data), 2):
        val = struct.unpack_from("<H", data, off)[0]
        u.write_u16(addr + off, val, delay=0.005, verify=True)


def _regions(payload, detour):
    return {
        "cave":  (CAVE,   payload),
        "patch": (TARGET, detour),
        "buf":   (BUF,    b"\x00" * BUF_LEN),
        "cnt":   (CNT,    b"\x00" * 4),
    }


def _save_baseline(u, regions):
    """只在首次部署时记录冷启动基线；重复部署不覆盖。"""
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as f:
            m = json.load(f)
        print(f"已有基线 manifest（{m['timestamp']}），沿用原始备份，不覆盖")
        return m
    m = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "regions": {}}
    for name, (addr, data) in regions.items():
        orig = u.read_mem(addr, len(data))
        bpath = os.path.join(ROOT, f"arb_{name}_baseline.json")
        with open(bpath, "w", encoding="utf-8") as f:
            json.dump({"addr": hex(addr), "length": len(orig),
                       "original_hex": orig.hex(), "timestamp": m["timestamp"]}, f, indent=2)
        m["regions"][name] = {"addr": hex(addr), "length": len(orig), "backup": bpath}
        print(f"  基线 {name:5s} {addr:#010x} {len(orig):3d}B -> {os.path.basename(bpath)}"
              f"  {orig[:12].hex(' ')}")
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2)
    return m


def preflight():
    print("=== 只读 preflight ===")
    with _usb() as u:
        print("device:", u.device_path[-56:])
        checks = [
            (TARGET,      4,  "detour 目标",      ORIG,            "干净基线"),
            (CAVE,        8,  "代码洞",           None,            "记录原貌"),
            (BUF,         8,  "BUF 区",           None,            "记录原貌"),
            (CNT,         4,  "CNT 区",           None,            "记录原貌"),
            (0x87086A00,  4,  "活动浮点表(禁写)", bytes.fromhex("cdcccc3d"), "必须完好"),
            (0x868F9A0C,  4,  "主核入口",         bytes.fromhex("820000ea"), "必须完好"),
            (0x866C22B4,  4,  "memcpy",           bytes.fromhex("030052e3"), "必须完好"),
            (0x86280000,  4,  "program 头",       bytes.fromhex("70f09fe5"), "必须完好"),
        ]
        ok = True
        for addr, n, label, expect, note in checks:
            d = u.read_mem(addr, n)
            good = True if expect is None else (d == expect)
            ok &= good
            print(f"  {addr:#010x} {d.hex(' '):<24} {label:<16} "
                  f"{'OK' if good else 'FAIL'}  {note}")
        cur = u.read_mem(TARGET, 4)
        if cur == build_detour():
            print("  注意: detour 已存在（重复部署为幂等操作）")
        elif cur != ORIG:
            print("  中止: 目标字节既非原厂也非本工具 patch"); ok = False
    print("PREFLIGHT", "PASS" if ok else "FAIL - 不要写入")
    return ok


def deploy(src):
    payload, detour = selftest(src)
    if not preflight():
        raise SystemExit("preflight 未通过，已中止")
    regions = _regions(payload, detour)
    print("\n=== 部署（RAM-only）===")
    with _usb() as u:
        _save_baseline(u, regions)
        for name, (addr, data) in regions.items():
            _write_bytes(u, addr, data)
            print(f"  写入 {name:5s} {addr:#010x} {len(data):3d}B")
    print("\n=== 读回校验 ===")
    ok = verify(quiet=False, src=src)
    print("\nDEPLOY", "OK" if ok else "FAILED")
    if ok:
        print("""
触发步骤（载荷挂在冷函数上，需相机实际执行该流程）：
  1. 电源键【热重启】到正常模式（切勿拔电池，拔电池会清空全部 RAM 补丁）
  2. SD 卡放官方 400BV020.plf，进固件更新菜单点【镜头更新】
     （镜头已装 Ver2.0，会提示"已安装"，但校验函数在提示前已被调用）
  3. 回服务模式 2370，执行: python arb_exec.py status
  4. 看到 MAGIC=0x45584543 且 cnt>=1，即证明任意载荷已在主核执行
  5. BUF+8 起的 32B 应与部署前 read_mem(SRC,32) 逐字节一致

回滚: python arb_exec.py rollback      (恢复部署前冷启动基线)
终极安全网: 拔电池冷启动会重载 RAM，清空所有补丁与证据
""")
    return ok


def verify(quiet=True, src=SRC_DEFAULT):
    payload, detour = build_payload(src), build_detour()
    regions = _regions(payload, detour)
    ok = True
    with _usb() as u:
        for name, (addr, data) in regions.items():
            live = u.read_mem(addr, len(data))
            good = live == data
            ok &= good
            if not quiet:
                print(f"  {name:5s} {addr:#010x} {'OK' if good else 'MISMATCH'}"
                      f"  {live[:12].hex(' ')}")
    if not quiet:
        print("VERIFY", "PASS" if ok else "FAIL")
    return ok


def status():
    with _usb() as u:
        b = u.read_mem(BUF, BUF_LEN)
        cnt = struct.unpack("<I", u.read_mem(CNT, 4))[0]
        magic = struct.unpack("<I", b[:4])[0]
        patch = u.read_mem(TARGET, 4)
        sig = u.read_mem(SIG_ADDR, 4)
    print(f"  detour @ {TARGET:#010x} = {patch.hex(' ')}  "
          f"({'已部署' if patch == build_detour() else '未部署/原厂'})")
    print(f"  MAGIC  @ {BUF:#010x} = {magic:#010x}  ({'已触发' if magic == MAGIC else '未触发'})")
    print(f"  CNT    @ {CNT:#010x} = {cnt}")
    print(f"  BUF+8  = {b[8:24].hex(' ')}")
    print(f"  BUF+24 = {b[24:40].hex(' ')}")
    print(f"  sig    @ {SIG_ADDR:#010x} = {sig.hex(' ')}  "
          f"({'恒真patch' if sig == SIG_PATCH else '原厂'})")
    return magic == MAGIC and cnt >= 1


def rollback():
    if not os.path.exists(MANIFEST):
        print("没有 manifest，无需回滚（可能从未部署）")
        return
    with open(MANIFEST, encoding="utf-8") as f:
        m = json.load(f)
    print(f"回滚到 {m['timestamp']} 的冷启动基线")
    with _usb() as u:
        for name, rec in m["regions"].items():
            with open(rec["backup"], encoding="utf-8") as f:
                b = json.load(f)
            orig = bytes.fromhex(b["original_hex"])
            addr = int(b["addr"], 16)
            _write_bytes(u, addr, orig)
            live = u.read_mem(addr, len(orig))
            print(f"  {name:5s} {addr:#010x} {'OK' if live == orig else 'MISMATCH'}")
    os.remove(MANIFEST)
    print("manifest 已删除，回滚完成")


# ---------------- 验签路径 ----------------
def sig_status():
    with _usb() as u:
        d = u.read_mem(SIG_ADDR, 4)
    state = "恒真 patch（验证恒返回有效）" if d == SIG_PATCH else (
        "原厂序言" if d == SIG_ORIG else "未知字节")
    print(f"  {SIG_ADDR:#010x} = {d.hex(' ')}  -> {state}")
    return d


def sig_on():
    with _usb() as u:
        # 复用已打开的连接，不能再调用 sig_status()（它会二次打开 WinUSB，err=5）
        cur = u.read_mem(SIG_ADDR, 4)
        state = "恒真 patch（验证恒返回有效）" if cur == SIG_PATCH else (
            "原厂序言" if cur == SIG_ORIG else "未知字节")
        print(f"  当前 {SIG_ADDR:#010x} = {cur.hex(' ')}  -> {state}")
        if cur == SIG_PATCH:
            print("已处于 patch 状态，无需重复写入")
            return
        if cur != SIG_ORIG:
            raise SystemExit("字节非原厂也非本工具 patch，中止")
        if not os.path.exists(SIG_BACKUP):
            with open(SIG_BACKUP, "w", encoding="utf-8") as f:
                json.dump({"addr": hex(SIG_ADDR), "original_hex": cur.hex(),
                           "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}, f, indent=2)
        _write_bytes(u, SIG_ADDR, SIG_PATCH)
        live = u.read_mem(SIG_ADDR, 4)
        print(f"  写入后 = {live.hex(' ')}  {'OK' if live == SIG_PATCH else 'MISMATCH'}")
    print("""
验签路径已改写（RAM-only）：
  movs r0,#0 ; bx lr  -> metadata ECDSA 校验恒返回"有效"
边界（重要）：该点属于【镜头固件升级】路径。机身固件更新的解密/验签在
  引导程序(postboot)中，明文仅在 NAND，本 patch 不能放行改过的机身包。
回滚: python arb_exec.py sig-off   或拔电池冷启动
""")


def sig_off():
    if not os.path.exists(SIG_BACKUP):
        print("没有验签备份，跳过")
        return
    with open(SIG_BACKUP, encoding="utf-8") as f:
        b = json.load(f)
    addr, orig = int(b["addr"], 16), bytes.fromhex(b["original_hex"])
    with _usb() as u:
        _write_bytes(u, addr, orig)
        print(f"  恢复 {addr:#010x} = {u.read_mem(addr, 4).hex(' ')}")
    os.remove(SIG_BACKUP)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["selftest", "preflight", "deploy", "verify",
                                    "status", "rollback", "sig-status", "sig-on", "sig-off"])
    ap.add_argument("--src", type=lambda x: int(x, 0), default=SRC_DEFAULT,
                    help=f"payload 复制源地址（默认 {SRC_DEFAULT:#x}）")
    a = ap.parse_args()
    fn = {
        "selftest":   lambda: selftest(a.src),
        "preflight":  preflight,
        "deploy":     lambda: deploy(a.src),
        "verify":     lambda: verify(quiet=False, src=a.src),
        "status":     status,
        "rollback":   rollback,
        "sig-status": sig_status,
        "sig-on":     sig_on,
        "sig-off":    sig_off,
    }[a.cmd]
    r = fn()
    if a.cmd in ("preflight", "deploy", "verify", "status") and r is False:
        sys.exit(1)


if __name__ == "__main__":
    main()
