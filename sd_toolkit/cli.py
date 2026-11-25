"""Command-line interface for LUMIX S5 SD-Card Modular Patch Toolkit."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .patch_format import decode_patches, encode_patches, to_service_va, verify_against_program_bin
from .profiles import DEFAULT_PROFILES_FILE, load_profiles, merge_profiles
from .sd_manager import (
    copy_official_firmware_to_sd,
    deploy_to_sd,
    detect_service_usb_devices,
    inspect_sd,
    list_removable_drives,
    revert_sd,
)

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROGRAM_BIN = WORKSPACE_ROOT / "analysis" / "decrypted_S5___V29" / "program.bin"


def cmd_drives(_args: argparse.Namespace) -> int:
    drives = list_removable_drives()
    if not drives:
        print("未检测到可移动磁盘 / SD 卡。")
    else:
        for d in drives:
            print(f"  {d.display_name}")
    usb = detect_service_usb_devices()
    print(f"Service USB (04DA:2370): {'已连接 (' + str(len(usb)) + ')' if usb else '未连接'}")
    if not usb:
        print("  提示：进入临时服务模式请先关机，右转轮调到 P 档、左转轮调到单拍，同时按住回放 + AF ON 键开机（否则会一直识别成其他模式）。")
    return 0


def cmd_list_profiles(args: argparse.Namespace) -> int:
    profiles = load_profiles(args.profiles)
    for p in profiles:
        print(f"[{p.id}] {p.name}")
        print(f"  分类: {p.category} | 风险: {p.risk} | 状态: {p.status}")
        print(f"  条目数: {len(p.entries)} | 说明: {p.description}")
    return 0


def cmd_verify_fw(args: argparse.Namespace) -> int:
    profiles = load_profiles(args.profiles)
    selected = [p for p in profiles if not args.profile or p.id in args.profile]
    if not selected:
        print("未匹配到任何档案。", file=sys.stderr)
        return 1
    entries = merge_profiles(selected)
    results = verify_against_program_bin(entries, args.program_bin)
    all_ok = True
    for e, ok, msg in results:
        mark = "OK  " if ok else "FAIL"
        print(f"[{mark}] VA=0x{e.target_va:08X} (svc 0x{to_service_va(e.target_va):08X}) "
              f"0x{e.expected_orig:04X}->0x{e.new_val:04X} | {msg}")
        if not ok:
            all_ok = False
    print(f"\nVERDICT: {'PASS' if all_ok else 'FAIL'} ({len(results)} entries)")
    return 0 if all_ok else 2


def cmd_build(args: argparse.Namespace) -> int:
    profiles = load_profiles(args.profiles)
    selected = [p for p in profiles if p.id in args.profile]
    if not selected:
        print("请通过 --profile 指定至少一个有效档案 ID。", file=sys.stderr)
        return 1
    entries = merge_profiles(selected)
    blob = encode_patches(entries)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    pkg = decode_patches(blob)
    print(f"已生成 {out} ({len(blob)} 字节, {len(pkg.entries)} 条目, CRC32=0x{pkg.payload_crc32:08X})")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    target = Path(args.target)
    if target.is_file():
        pkg = decode_patches(target.read_bytes())
        print(f"文件: {target}")
        print(f"  格式版本: 0x{pkg.format_ver:04X} | 目标固件: 0x{pkg.fw_version:08X} | "
              f"标志: 0x{pkg.flags:04X} | CRC32: 0x{pkg.payload_crc32:08X}")
        for i, e in enumerate(pkg.entries):
            print(f"  [{i}] VA=0x{e.target_va:08X} (svc 0x{to_service_va(e.target_va):08X}) "
                  f"orig=0x{e.expected_orig:04X} -> new=0x{e.new_val:04X}")
        return 0
    info = inspect_sd(target)
    print(f"SD 根目录: {info['sd_root']}")
    print(f"  LUMIX_ML 目录: {'存在' if info['ml_dir_exists'] else '不存在'}")
    print(f"  PATCHES.BIN : {'存在' if info['patches_exists'] else '未部署 (原厂状态)'}")
    if info["error"]:
        print(f"  校验错误: {info['error']}", file=sys.stderr)
        return 2
    if info["package"]:
        pkg = info["package"]
        print(f"  校验通过: {len(pkg.entries)} 条目, 目标固件 0x{pkg.fw_version:08X}, CRC32=0x{pkg.payload_crc32:08X}")
        for i, e in enumerate(pkg.entries):
            print(f"    [{i}] VA=0x{e.target_va:08X} 0x{e.expected_orig:04X} -> 0x{e.new_val:04X}")
    return 0


def cmd_deploy(args: argparse.Namespace) -> int:
    profiles = load_profiles(args.profiles)
    selected = [p for p in profiles if p.id in args.profile]
    if not selected:
        print("请通过 --profile 指定至少一个有效档案 ID。", file=sys.stderr)
        return 1
    res = deploy_to_sd(args.sd_root, selected)
    print(f"部署成功 -> {res['patches_path']}")
    print(f"  大小: {res['bytes_written']} 字节 | 条目数: {res['entry_count']} | CRC32: 0x{res['payload_crc32']:08X}")
    if res["backup_path"]:
        print(f"  已自动备份旧文件 -> {res['backup_path']}")
    return 0


def cmd_revert(args: argparse.Namespace) -> int:
    res = revert_sd(args.sd_root)
    if res["removed"]:
        print(f"已移除 PATCHES.BIN（恢复原厂状态），旧文件已备份至 {res['backup_path']}")
    else:
        print("未发现 PATCHES.BIN，当前已为原厂状态。")
    return 0


def cmd_restore_fw(args: argparse.Namespace) -> int:
    res = copy_official_firmware_to_sd(args.sd_root, args.fw)
    print(f"已复制官方固件 -> {res['dst']} ({res['size']:,} 字节)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lumix-sd-tool", description="LUMIX S5 SD 卡模块化补丁基座 CLI")
    p.add_argument("--profiles", default=str(DEFAULT_PROFILES_FILE), help="档案 JSON 路径")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("drives", help="扫描可移动磁盘与 Service USB 状态").set_defaults(func=cmd_drives)
    sub.add_parser("list-profiles", help="列出可用功能档案").set_defaults(func=cmd_list_profiles)

    pv = sub.add_parser("verify-fw", help="对照本地明文 program.bin 离线核验原厂半字")
    pv.add_argument("--profile", action="append", default=[], help="指定档案 ID（可多次）")
    pv.add_argument("--program-bin", default=str(DEFAULT_PROGRAM_BIN), help="明文 program.bin 路径")
    pv.set_defaults(func=cmd_verify_fw)

    pb = sub.add_parser("build", help="构建独立的 PATCHES.BIN 文件")
    pb.add_argument("--profile", action="append", required=True, help="档案 ID（可多次）")
    pb.add_argument("--out", required=True, help="输出 PATCHES.BIN 路径")
    pb.set_defaults(func=cmd_build)

    pi = sub.add_parser("inspect", help="解析 SD 卡目录或单个 PATCHES.BIN 文件")
    pi.add_argument("target", help="SD 卡根目录或 PATCHES.BIN 路径")
    pi.set_defaults(func=cmd_inspect)

    pd = sub.add_parser("deploy", help="部署选定档案到 SD 卡 LUMIX_ML/PATCHES.BIN")
    pd.add_argument("sd_root", help="SD 卡根目录（如 H:\\ 或测试目录）")
    pd.add_argument("--profile", action="append", required=True, help="档案 ID（可多次）")
    pd.set_defaults(func=cmd_deploy)

    pr = sub.add_parser("revert", help="备份并移除 SD 卡 PATCHES.BIN（恢复原厂）")
    pr.add_argument("sd_root", help="SD 卡根目录")
    pr.set_defaults(func=cmd_revert)

    pf = sub.add_parser("restore-fw", help="复制官方固件到 SD 卡根目录用于官方恢复")
    pf.add_argument("sd_root", help="SD 卡根目录")
    pf.add_argument("--fw", default=str(WORKSPACE_ROOT / "S5___V29.bin"), help="官方固件路径")
    pf.set_defaults(func=cmd_restore_fw)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (FileNotFoundError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
