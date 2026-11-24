"""SD card discovery, atomic PATCHES.BIN deployment, inspection, and recovery helpers."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import string
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

from .patch_format import (
    FLAG_ENABLE_LOG,
    FW_VER_S5_V29,
    PatchEntry,
    PatchPackage,
    decode_patches,
    encode_patches,
)
from .profiles import FeatureProfile, merge_profiles

ML_DIR_NAME = "LUMIX_ML"
PATCHES_FILE_NAME = "PATCHES.BIN"
MANIFEST_FILE_NAME = "manifest.json"
BOOT_LOG_NAME = "BOOT.LOG"
BACKUP_DIR_NAME = "backups"

DRIVE_REMOVABLE = 2


@dataclass(frozen=True)
class DriveInfo:
    root: Path
    label: str
    fs_type: str
    is_removable: bool
    has_dcim: bool
    has_lumix_ml: bool
    free_bytes: int

    @property
    def display_name(self) -> str:
        gb = self.free_bytes / (1024 ** 3)
        tag = " [LUMIX SD]" if self.has_dcim else (" [ML]" if self.has_lumix_ml else "")
        lbl = self.label or "无卷标"
        return f"{self.root} ({lbl}, {self.fs_type or '?'}, 可用 {gb:.1f} GB){tag}"


def list_removable_drives() -> List[DriveInfo]:
    """Enumerate Windows removable drives (SD cards / USB readers) with zero dependencies."""
    if os.name != "nt":
        return []
    kernel32 = ctypes.windll.kernel32
    bitmask = kernel32.GetLogicalDrives()
    drives: List[DriveInfo] = []
    for idx, letter in enumerate(string.ascii_uppercase):
        if not (bitmask & (1 << idx)):
            continue
        root_str = f"{letter}:\\"
        dtype = kernel32.GetDriveTypeW(root_str)
        if dtype != DRIVE_REMOVABLE:
            continue
        vol_buf = ctypes.create_unicode_buffer(261)
        fs_buf = ctypes.create_unicode_buffer(261)
        ok = kernel32.GetVolumeInformationW(
            root_str, vol_buf, 261, None, None, None, fs_buf, 261
        )
        if not ok:
            # Empty card reader slot (no media inserted)
            continue
        free_bytes = ctypes.c_ulonglong(0)
        kernel32.GetDiskFreeSpaceExW(root_str, ctypes.byref(free_bytes), None, None)
        root_path = Path(root_str)
        drives.append(
            DriveInfo(
                root=root_path,
                label=vol_buf.value,
                fs_type=fs_buf.value,
                is_removable=True,
                has_dcim=(root_path / "DCIM").is_dir(),
                has_lumix_ml=(root_path / ML_DIR_NAME).is_dir(),
                free_bytes=free_bytes.value,
            )
        )
    return drives


def detect_service_usb_devices() -> List[str]:
    """Read-only check for *currently connected* LUMIX S5 Service Mode (VID_04DA&PID_2370).

    Uses SetupAPI (DIGCF_PRESENT) exclusively to avoid false positives from stale
    Windows Registry DeviceClasses entries left behind after unplugging.
    """
    workspace_root = Path(__file__).resolve().parent.parent
    lumix_ml_dir = workspace_root / "lumix_ml"
    if not lumix_ml_dir.is_dir():
        return []
    try:
        if str(lumix_ml_dir) not in sys.path:
            sys.path.insert(0, str(lumix_ml_dir))
        import usb_link  # type: ignore
        if hasattr(usb_link, "_find_via_setupapi"):
            return list(usb_link._find_via_setupapi())
        return []
    except Exception:
        return []


def _backup_existing(patches_path: Path) -> Optional[Path]:
    if not patches_path.is_file():
        return None
    bdir = patches_path.parent / BACKUP_DIR_NAME
    bdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = bdir / f"PATCHES_{ts}.BIN"
    shutil.copy2(patches_path, dst)
    return dst


def deploy_to_sd(
    sd_root: str | Path,
    profiles: Sequence[FeatureProfile],
    extra_entries: Sequence[PatchEntry] = (),
    fw_version: int = FW_VER_S5_V29,
    enable_log: bool = True,
) -> dict:
    """Build and atomically write SD:/LUMIX_ML/PATCHES.BIN + manifest.json."""
    root = Path(sd_root)
    if not root.exists():
        raise FileNotFoundError(f"目标路径不存在: {root}")

    entries = merge_profiles(profiles)
    if extra_entries:
        from .patch_format import validate_entries
        entries = validate_entries(list(entries) + list(extra_entries))

    flags = FLAG_ENABLE_LOG if enable_log else 0
    blob = encode_patches(entries, fw_version=fw_version, flags=flags)
    # Self-verify round-trip before touching the SD card
    decoded = decode_patches(blob)

    ml_dir = root / ML_DIR_NAME
    ml_dir.mkdir(parents=True, exist_ok=True)
    patches_path = ml_dir / PATCHES_FILE_NAME
    backup_path = _backup_existing(patches_path)

    tmp_path = ml_dir / f".{PATCHES_FILE_NAME}.tmp"
    tmp_path.write_bytes(blob)
    os.replace(tmp_path, patches_path)

    manifest = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "fw_version": f"0x{fw_version:08X}",
        "flags": flags,
        "entry_count": len(decoded.entries),
        "payload_crc32": f"0x{decoded.payload_crc32:08X}",
        "sha256": hashlib.sha256(blob).hexdigest(),
        "profiles": [{"id": p.id, "name": p.name} for p in profiles],
    }
    manifest_path = ml_dir / MANIFEST_FILE_NAME
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "patches_path": str(patches_path),
        "manifest_path": str(manifest_path),
        "backup_path": str(backup_path) if backup_path else None,
        "bytes_written": len(blob),
        "entry_count": len(decoded.entries),
        "payload_crc32": decoded.payload_crc32,
    }


def inspect_sd(sd_root: str | Path) -> dict:
    """Read and validate existing LUMIX_ML deployment on an SD card / directory."""
    root = Path(sd_root)
    ml_dir = root / ML_DIR_NAME
    patches_path = ml_dir / PATCHES_FILE_NAME
    manifest_path = ml_dir / MANIFEST_FILE_NAME
    boot_log_path = ml_dir / BOOT_LOG_NAME

    info: dict = {
        "sd_root": str(root),
        "ml_dir_exists": ml_dir.is_dir(),
        "patches_exists": patches_path.is_file(),
        "package": None,
        "error": None,
        "manifest": None,
        "boot_log": None,
    }
    if manifest_path.is_file():
        try:
            info["manifest"] = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            info["manifest"] = {"parse_error": str(exc)}
    if boot_log_path.is_file():
        try:
            info["boot_log"] = boot_log_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if patches_path.is_file():
        try:
            pkg: PatchPackage = decode_patches(patches_path.read_bytes())
            info["package"] = pkg
        except Exception as exc:
            info["error"] = str(exc)
    return info


def revert_sd(sd_root: str | Path) -> dict:
    """Disable SD patches by backing up and removing SD:/LUMIX_ML/PATCHES.BIN."""
    root = Path(sd_root)
    patches_path = root / ML_DIR_NAME / PATCHES_FILE_NAME
    if not patches_path.is_file():
        return {"removed": False, "backup_path": None}
    backup_path = _backup_existing(patches_path)
    patches_path.unlink()
    return {"removed": True, "backup_path": str(backup_path) if backup_path else None}


def copy_official_firmware_to_sd(sd_root: str | Path, official_fw_path: str | Path) -> dict:
    """Copy stock S5___V29.bin to SD root for official firmware restoration."""
    src = Path(official_fw_path)
    if not src.is_file():
        raise FileNotFoundError(f"未找到官方固件文件: {src}")
    root = Path(sd_root)
    if not root.exists():
        raise FileNotFoundError(f"目标 SD 卡路径不存在: {root}")
    dst = root / src.name
    shutil.copy2(src, dst)
    return {"src": str(src), "dst": str(dst), "size": dst.stat().st_size}
