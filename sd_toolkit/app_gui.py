"""Zero-dependency Tkinter desktop GUI for LUMIX S5 SD-Card Modular Patch Toolkit."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List

from . import __version__
from .patch_format import (
    PatchValidationError,
    decode_patches,
    to_service_va,
    verify_against_program_bin,
)
from .profiles import DEFAULT_PROFILES_FILE, FeatureProfile, load_profiles, merge_profiles
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
DEFAULT_OFFICIAL_FW = WORKSPACE_ROOT / "S5___V29.bin"


class LumixSDToolApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"LUMIX S5 SD 卡模块化基座工具 v{__version__}")
        self.geometry("920x660")
        self.minsize(820, 580)

        self.profiles_path = DEFAULT_PROFILES_FILE
        self.profiles: List[FeatureProfile] = []
        self.profile_vars: Dict[str, tk.BooleanVar] = {}
        self.drive_map: Dict[str, Path] = {}

        self._build_ui()
        self._load_profiles_into_ui(self.profiles_path)
        self._refresh_drives()
        self._refresh_usb_status()

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_sd = ttk.Frame(notebook, padding=10)
        self.tab_base = ttk.Frame(notebook, padding=10)
        self.tab_inspect = ttk.Frame(notebook, padding=10)

        notebook.add(self.tab_sd, text="  1. SD 卡功能管理 (日常免 USB)  ")
        notebook.add(self.tab_base, text="  2. 基座激活与官方恢复  ")
        notebook.add(self.tab_inspect, text="  3. PATCHES.BIN 校验与日志  ")

        self._build_sd_tab()
        self._build_base_tab()
        self._build_inspect_tab()

    # ---------------- Tab 1: SD Card Management ----------------
    def _build_sd_tab(self) -> None:
        top = ttk.LabelFrame(self.tab_sd, text="目标 SD 卡 / 模拟目录", padding=8)
        top.pack(fill="x", pady=(0, 8))

        self.sd_var = tk.StringVar()
        self.drive_combo = ttk.Combobox(top, textvariable=self.sd_var, width=58)
        self.drive_combo.pack(side="left", fill="x", expand=True, padx=(0, 6))

        ttk.Button(top, text="刷新磁盘", command=self._refresh_drives).pack(side="left", padx=2)
        ttk.Button(top, text="选择目录...", command=self._choose_sd_dir).pack(side="left", padx=2)
        ttk.Button(top, text="读取卡内状态", command=self._inspect_current_sd).pack(side="left", padx=2)

        mid = ttk.PanedWindow(self.tab_sd, orient="horizontal")
        mid.pack(fill="both", expand=True, pady=(0, 8))

        # Left: Feature profile checkboxes
        left = ttk.LabelFrame(mid, text="可用功能档案 (V2.9)", padding=8)
        mid.add(left, weight=2)

        self.profile_list_frame = ttk.Frame(left)
        self.profile_list_frame.pack(fill="both", expand=True)

        prof_btns = ttk.Frame(left)
        prof_btns.pack(fill="x", pady=(6, 0))
        ttk.Button(prof_btns, text="导入自定义 JSON...", command=self._import_profiles_json).pack(side="left")

        # Right: Entry preview table
        right = ttk.LabelFrame(mid, text="待写入补丁明细 (主核 VA / 原值 -> 新值)", padding=8)
        mid.add(right, weight=3)

        cols = ("va", "svc", "orig", "new", "note")
        self.entry_tree = ttk.Treeview(right, columns=cols, show="headings", height=12)
        self.entry_tree.heading("va", text="主核 VA")
        self.entry_tree.heading("svc", text="Service 别名")
        self.entry_tree.heading("orig", text="期望原值")
        self.entry_tree.heading("new", text="写入新值")
        self.entry_tree.heading("note", text="说明")
        self.entry_tree.column("va", width=95, anchor="center")
        self.entry_tree.column("svc", width=95, anchor="center")
        self.entry_tree.column("orig", width=75, anchor="center")
        self.entry_tree.column("new", width=75, anchor="center")
        self.entry_tree.column("note", width=210, anchor="w")
        self.entry_tree.pack(fill="both", expand=True)

        # Bottom action bar
        bar = ttk.Frame(self.tab_sd)
        bar.pack(fill="x")

        self.enable_log_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="开启 SD:/LUMIX_ML/BOOT.LOG 诊断日志", variable=self.enable_log_var).pack(side="left")

        ttk.Button(bar, text="禁用/恢复原厂 (移除 PATCHES.BIN)", command=self._revert_current_sd).pack(side="right", padx=4)
        ttk.Button(bar, text="一键部署到 SD 卡", command=self._deploy_current_sd).pack(side="right", padx=4)
        ttk.Button(bar, text="离线核验原厂固件", command=self._verify_against_fw).pack(side="right", padx=4)

        self.status_var = tk.StringVar(value="就绪：请选择 SD 卡或离线测试目录。")
        ttk.Label(self.tab_sd, textvariable=self.status_var, foreground="#1f4e79").pack(fill="x", pady=(6, 0))

    # ---------------- Tab 2: Base Activation & Recovery ----------------
    def _build_base_tab(self) -> None:
        usb_box = ttk.LabelFrame(self.tab_base, text="相机 Service USB 状态 (仅首次激活基座时使用，日常免插线)", padding=10)
        usb_box.pack(fill="x", pady=(0, 10))

        usb_top = ttk.Frame(usb_box)
        usb_top.pack(fill="x")
        self.usb_status_var = tk.StringVar(value="正在检测...")
        ttk.Label(usb_top, textvariable=self.usb_status_var).pack(side="left", fill="x", expand=True)
        ttk.Button(usb_top, text="刷新 USB 检测", command=self._refresh_usb_status).pack(side="right")

        ttk.Label(
            usb_box,
            text="进入临时服务模式提示：右转轮调到 P 档，左转轮调到单拍，关机后同时按住回放 + AF ON 键开机（否则会一直识别成其他模式）。",
            foreground="#8a4b00",
            wraplength=920,
        ).pack(fill="x", pady=(6, 0))

        guide_box = ttk.LabelFrame(self.tab_base, text="一次性基座激活安全流程 (离线参考清单)", padding=10)
        guide_box.pack(fill="both", expand=True, pady=(0, 10))

        guide_text = (
            "1. 【阶段 1 · 前置回滚演练】确认手中保留官方 S5___V29.bin，并验证相机可正常刷回官方固件。\n"
            "2. 【阶段 2 · 唯一一次基座写入】在真机就绪后，通过一次最小化引导固件更新，将极简 SD Loader 写入机身。\n"
            "   - SD Loader 开机自动检查 SD:\\LUMIX_ML\\PATCHES.BIN。\n"
            "   - 四重防砖保护：无文件直接走原厂；校验 Magic + 固件版本 + CRC32 + 原厂半字一致后才应用。\n"
            "3. 【阶段 3 · 彻底脱离 USB 服务模式】此后所有功能开关、增删改，均只需插读卡器在本工具 Tab 1 中操作。\n"
            "   - 拔掉 SD 卡或删除 PATCHES.BIN，开机即 100% 恢复原厂状态。"
        )
        txt = tk.Text(guide_box, height=9, wrap="word", relief="flat", background="#f7f7f7")
        txt.insert("1.0", guide_text)
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True)

        rec_box = ttk.LabelFrame(self.tab_base, text="官方原厂固件恢复 (S5___V29.bin)", padding=10)
        rec_box.pack(fill="x")

        self.official_fw_var = tk.StringVar(value=str(DEFAULT_OFFICIAL_FW))
        ttk.Entry(rec_box, textvariable=self.official_fw_var).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(rec_box, text="浏览...", command=self._choose_official_fw).pack(side="left", padx=2)
        ttk.Button(rec_box, text="复制到当前 SD 卡根目录", command=self._copy_official_fw).pack(side="left", padx=2)

    # ---------------- Tab 3: Inspect & Log ----------------
    def _build_inspect_tab(self) -> None:
        bar = ttk.Frame(self.tab_inspect)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="解析任意 PATCHES.BIN 文件...", command=self._inspect_patch_file).pack(side="left")
        ttk.Button(bar, text="清空日志", command=lambda: self.log_text.delete("1.0", "end")).pack(side="right")

        self.log_text = tk.Text(self.tab_inspect, wrap="word", font=("Consolas", 10))
        self.log_text.pack(fill="both", expand=True)

    # ---------------- Helpers & Actions ----------------
    def _log(self, msg: str) -> None:
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")

    def _resolve_sd_root(self) -> Path | None:
        raw = self.sd_var.get().strip()
        if not raw:
            messagebox.showwarning("提示", "请先选择一个 SD 卡盘符或目录。")
            return None
        if raw in self.drive_map:
            return self.drive_map[raw]
        return Path(raw)

    def _selected_profiles(self) -> List[FeatureProfile]:
        return [p for p in self.profiles if self.profile_vars.get(p.id) and self.profile_vars[p.id].get()]

    def _load_profiles_into_ui(self, path: Path) -> None:
        for child in self.profile_list_frame.winfo_children():
            child.destroy()
        self.profile_vars.clear()
        self.profiles = load_profiles(path)
        for p in self.profiles:
            var = tk.BooleanVar(value=True)
            self.profile_vars[p.id] = var
            row = ttk.Frame(self.profile_list_frame)
            row.pack(fill="x", pady=3)
            cb = ttk.Checkbutton(row, text=f"{p.name} ({len(p.entries)} 条)", variable=var, command=self._refresh_entry_preview)
            cb.pack(anchor="w")
            ttk.Label(row, text=f"  {p.category} | {p.risk} | {p.status}", foreground="#555555").pack(anchor="w")
        self._refresh_entry_preview()
        self._log(f"[档案] 已加载 {len(self.profiles)} 个功能档案: {path}")

    def _refresh_entry_preview(self) -> None:
        for item in self.entry_tree.get_children():
            self.entry_tree.delete(item)
        selected = self._selected_profiles()
        if not selected:
            self.status_var.set("当前未勾选任何功能档案。")
            return
        try:
            entries = merge_profiles(selected)
        except PatchValidationError as exc:
            self.status_var.set(f"校验冲突: {exc}")
            messagebox.showerror("补丁校验失败", str(exc))
            return
        for e in entries:
            self.entry_tree.insert(
                "",
                "end",
                values=(
                    f"0x{e.target_va:08X}",
                    f"0x{to_service_va(e.target_va):08X}",
                    f"0x{e.expected_orig:04X}",
                    f"0x{e.new_val:04X}",
                    e.note,
                ),
            )
        self.status_var.set(f"已选 {len(selected)} 个档案，共 {len(entries)} 条安全补丁（已通过禁写区与冲突检查）。")

    def _refresh_drives(self) -> None:
        drives = list_removable_drives()
        self.drive_map = {d.display_name: d.root for d in drives}
        values = list(self.drive_map.keys())
        self.drive_combo["values"] = values
        if values:
            self.sd_var.set(values[0])
            self._log(f"[磁盘] 检测到 {len(values)} 个可移动磁盘: {', '.join(str(d.root) for d in drives)}")
        else:
            self._log("[磁盘] 未检测到可移动 SD 卡，可点击「选择目录...」进行离线测试。")

    def _choose_sd_dir(self) -> None:
        chosen = filedialog.askdirectory(title="选择 SD 卡根目录或离线测试目录")
        if chosen:
            self.sd_var.set(chosen)

    def _import_profiles_json(self) -> None:
        chosen = filedialog.askopenfilename(
            title="选择功能档案 JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if chosen:
            try:
                self._load_profiles_into_ui(Path(chosen))
            except Exception as exc:
                messagebox.showerror("加载失败", str(exc))

    def _verify_against_fw(self) -> None:
        selected = self._selected_profiles()
        if not selected:
            messagebox.showinfo("提示", "请先勾选至少一个功能档案。")
            return
        fw_path = DEFAULT_PROGRAM_BIN
        if not fw_path.is_file():
            chosen = filedialog.askopenfilename(title="选择明文 program.bin")
            if not chosen:
                return
            fw_path = Path(chosen)
        try:
            entries = merge_profiles(selected)
            results = verify_against_program_bin(entries, fw_path)
        except Exception as exc:
            messagebox.showerror("核验出错", str(exc))
            return
        ok_cnt = sum(1 for _, ok, _ in results if ok)
        lines = [f"核验对象: {fw_path}"]
        for e, ok, msg in results:
            lines.append(f"[{'PASS' if ok else 'FAIL'}] 0x{e.target_va:08X} {msg}")
        report = "\n".join(lines)
        self._log("\n" + report)
        if ok_cnt == len(results):
            messagebox.showinfo("离线核验通过", f"全部 {ok_cnt}/{len(results)} 条原厂半字与明文 program.bin 逐项匹配！")
        else:
            messagebox.showerror("离线核验未通过", f"仅 {ok_cnt}/{len(results)} 条匹配，详情见日志页。")

    def _deploy_current_sd(self) -> None:
        root = self._resolve_sd_root()
        if not root:
            return
        selected = self._selected_profiles()
        if not selected:
            messagebox.showwarning("提示", "请先勾选至少一个功能档案。")
            return
        try:
            res = deploy_to_sd(root, selected, enable_log=self.enable_log_var.get())
        except Exception as exc:
            messagebox.showerror("部署失败", str(exc))
            return
        msg = (
            f"部署成功！\n"
            f"路径: {res['patches_path']}\n"
            f"大小: {res['bytes_written']} 字节 | 条目: {res['entry_count']}\n"
            f"CRC32: 0x{res['payload_crc32']:08X}"
        )
        if res["backup_path"]:
            msg += f"\n旧文件已自动备份至: {res['backup_path']}"
        self._log("[部署] " + msg.replace("\n", " | "))
        self.status_var.set(f"已部署 {res['entry_count']} 条补丁至 {res['patches_path']}")
        messagebox.showinfo("部署成功", msg)

    def _inspect_current_sd(self) -> None:
        root = self._resolve_sd_root()
        if not root:
            return
        info = inspect_sd(root)
        lines = [f"[读取卡内状态] {info['sd_root']}"]
        if not info["patches_exists"]:
            lines.append("  未发现 LUMIX_ML/PATCHES.BIN（当前为原厂无补丁状态）。")
        elif info["error"]:
            lines.append(f"  PATCHES.BIN 校验失败: {info['error']}")
        else:
            pkg = info["package"]
            lines.append(
                f"  PATCHES.BIN 有效: 目标固件 0x{pkg.fw_version:08X}, "
                f"{len(pkg.entries)} 条目, CRC32=0x{pkg.payload_crc32:08X}"
            )
            for i, e in enumerate(pkg.entries):
                lines.append(f"    [{i}] VA=0x{e.target_va:08X} 0x{e.expected_orig:04X} -> 0x{e.new_val:04X}")
        report = "\n".join(lines)
        self._log(report)
        messagebox.showinfo("SD 卡状态", report)

    def _revert_current_sd(self) -> None:
        root = self._resolve_sd_root()
        if not root:
            return
        res = revert_sd(root)
        if res["removed"]:
            msg = f"已移除 PATCHES.BIN，插回相机即恢复原厂。\n备份位置: {res['backup_path']}"
            self._log("[恢复原厂] " + msg.replace("\n", " | "))
            self.status_var.set("已移除 PATCHES.BIN（原厂状态）。")
            messagebox.showinfo("已恢复原厂", msg)
        else:
            messagebox.showinfo("提示", "当前目录未发现 PATCHES.BIN，已是原厂状态。")

    def _refresh_usb_status(self) -> None:
        devs = detect_service_usb_devices()
        if devs:
            self.usb_status_var.set(f"已检测到 Service Mode 相机 (04DA:2370): {len(devs)} 台")
        else:
            self.usb_status_var.set("未检测到临时服务模式相机（请确认右转轮 P 档 + 左转轮单拍，按住回放 + AF ON 开机；离线模式可正常管理 SD 卡）")

    def _choose_official_fw(self) -> None:
        chosen = filedialog.askopenfilename(title="选择官方固件 S5___V29.bin", filetypes=[("BIN files", "*.bin")])
        if chosen:
            self.official_fw_var.set(chosen)

    def _copy_official_fw(self) -> None:
        root = self._resolve_sd_root()
        if not root:
            return
        try:
            res = copy_official_firmware_to_sd(root, self.official_fw_var.get().strip())
        except Exception as exc:
            messagebox.showerror("复制失败", str(exc))
            return
        msg = f"已将官方固件复制到 {res['dst']} ({res['size']:,} 字节)"
        self._log("[官方恢复] " + msg)
        messagebox.showinfo("复制完成", msg)

    def _inspect_patch_file(self) -> None:
        chosen = filedialog.askopenfilename(title="选择 PATCHES.BIN 文件", filetypes=[("BIN files", "*.bin"), ("All", "*.*")])
        if not chosen:
            return
        try:
            pkg = decode_patches(Path(chosen).read_bytes())
        except Exception as exc:
            self._log(f"[解析失败] {chosen}: {exc}")
            messagebox.showerror("解析失败", str(exc))
            return
        lines = [
            f"[解析通过] {chosen}",
            f"  格式: 0x{pkg.format_ver:04X} | 固件: 0x{pkg.fw_version:08X} | 标志: 0x{pkg.flags:04X} | CRC32: 0x{pkg.payload_crc32:08X}",
        ]
        for i, e in enumerate(pkg.entries):
            lines.append(f"  [{i}] VA=0x{e.target_va:08X} (svc 0x{to_service_va(e.target_va):08X}) 0x{e.expected_orig:04X} -> 0x{e.new_val:04X}")
        self._log("\n".join(lines))


def main() -> None:
    app = LumixSDToolApp()
    app.mainloop()


if __name__ == "__main__":
    main()
