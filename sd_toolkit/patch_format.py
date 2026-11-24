"""Declarative PATCHES.BIN (LMLX) binary protocol, CRC32 & safety validator.

Binary layout (little-endian):
  Header (24 bytes):
    0x00  4B  magic         = b"LMLX" (0x584C4D4C)
    0x04  2B  format_ver    = 0x0001
    0x06  2B  flags         = bit0: enable boot.log output
    0x08  4B  fw_version    = 0x00000290 (V2.90)
    0x0C  4B  entry_count   = N (<= MAX_ENTRIES)
    0x10  4B  payload_crc32 = zlib.crc32(entries_bytes) & 0xFFFFFFFF
    0x14  4B  reserved      = 0

  Entry (8 bytes each, N entries):
    +0x00 4B  target_va     = main-core runtime VA (e.g. 0x06E3DB1C)
    +0x04 2B  expected_orig = expected original u16 halfword before write
    +0x06 2B  new_val       = replacement u16 halfword
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

MAGIC = b"LMLX"
FORMAT_VER = 0x0001
FW_VER_S5_V29 = 0x00000290
MAX_ENTRIES = 256

FLAG_ENABLE_LOG = 0x0001

HEADER_STRUCT = struct.Struct("<4sHHIIII")  # 24 bytes
ENTRY_STRUCT = struct.Struct("<IHH")       # 8 bytes

# Main-core program.bin mapping constants (V2.9)
MAIN_VA_BASE = 0x06280000
SVC_VA_BASE = 0x86280000
PROGRAM_MAX_SIZE = 0x01000000  # 16 MiB window (V2.9 program.bin is 16,674,816 B)

# Safe writable main-core VA window for declarative program data patches
SAFE_VA_MIN = MAIN_VA_BASE + 0x00000010
SAFE_VA_MAX = 0x0BFFFFFE  # Strictly below unmapped blackhole >= 0x0C000000

# Known forbidden active code/data ranges (in main-core VA) documented in project handoffs
FORBIDDEN_RANGES: Tuple[Tuple[int, int, str], ...] = (
    (0x06280000, 0x06280010, "program.bin 入口头 (禁写)"),
    (0x066C22B4, 0x066C22BC, "memcpy 核心例程 (禁写)"),
    (0x068F9A0C, 0x068F9A14, "主核入口点 (禁写)"),
    (0x07086400, 0x07086500, "活动浮点常量表 0x87086400 (禁写)"),
    (0x07086A00, 0x07086B00, "活动浮点常量表 0x87086A00 (禁写)"),
)


class PatchValidationError(ValueError):
    """Raised when a patch entry or PATCHES.BIN blob fails safety/integrity checks."""


def normalize_to_main_va(addr: int) -> int:
    """Convert Service USB alias (0x8xxxxxxx) to main-core runtime VA (0x0xxxxxxx).

    Addresses already in 0x0xxxxxxx are returned unchanged.
    """
    if 0x80000000 <= addr < 0x90000000:
        return addr - 0x80000000
    return addr


def to_service_va(main_va: int) -> int:
    """Convert main-core runtime VA (0x0xxxxxxx) to Service USB alias (0x8xxxxxxx)."""
    if 0x00000000 <= main_va < 0x10000000:
        return main_va + 0x80000000
    return main_va


@dataclass(frozen=True)
class PatchEntry:
    target_va: int
    expected_orig: int
    new_val: int
    note: str = ""

    def normalized(self) -> "PatchEntry":
        return PatchEntry(
            target_va=normalize_to_main_va(self.target_va),
            expected_orig=self.expected_orig & 0xFFFF,
            new_val=self.new_val & 0xFFFF,
            note=self.note,
        )

    def validate(self) -> None:
        va = normalize_to_main_va(self.target_va)
        if va & 1:
            raise PatchValidationError(f"地址未按 2 字节对齐: 0x{va:08X}")
        if va < SAFE_VA_MIN or va > SAFE_VA_MAX:
            raise PatchValidationError(
                f"地址超出安全允许区间 [0x{SAFE_VA_MIN:08X}, 0x{SAFE_VA_MAX:08X}]: 0x{va:08X}"
            )
        for lo, hi, reason in FORBIDDEN_RANGES:
            if lo <= va < hi:
                raise PatchValidationError(f"命中禁写区 0x{va:08X}: {reason}")
        if not (0 <= self.expected_orig <= 0xFFFF):
            raise PatchValidationError(f"expected_orig 超出 u16 范围: {self.expected_orig}")
        if not (0 <= self.new_val <= 0xFFFF):
            raise PatchValidationError(f"new_val 超出 u16 范围: {self.new_val}")


@dataclass(frozen=True)
class PatchPackage:
    fw_version: int
    flags: int
    entries: Tuple[PatchEntry, ...]
    format_ver: int = FORMAT_VER
    payload_crc32: Optional[int] = None


def validate_entries(entries: Sequence[PatchEntry]) -> List[PatchEntry]:
    """Normalize, validate safety ranges, and detect duplicate target addresses."""
    if len(entries) > MAX_ENTRIES:
        raise PatchValidationError(f"补丁条目数 {len(entries)} 超过上限 {MAX_ENTRIES}")
    seen: dict[int, PatchEntry] = {}
    out: List[PatchEntry] = []
    for raw in entries:
        e = raw.normalized()
        e.validate()
        if e.target_va in seen:
            prev = seen[e.target_va]
            if prev.new_val == e.new_val and prev.expected_orig == e.expected_orig:
                continue  # Identical duplicate, safely deduplicate
            raise PatchValidationError(
                f"地址冲突 0x{e.target_va:08X}: 已有写入 0x{prev.new_val:04X}, 冲突写入 0x{e.new_val:04X}"
            )
        seen[e.target_va] = e
        out.append(e)
    return out


def encode_patches(
    entries: Iterable[PatchEntry],
    fw_version: int = FW_VER_S5_V29,
    flags: int = FLAG_ENABLE_LOG,
) -> bytes:
    """Serialize validated entries into an LMLX PATCHES.BIN byte buffer."""
    norm = validate_entries(list(entries))
    payload = bytearray()
    for e in norm:
        payload.extend(ENTRY_STRUCT.pack(e.target_va, e.expected_orig, e.new_val))
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    header = HEADER_STRUCT.pack(
        MAGIC,
        FORMAT_VER,
        flags & 0xFFFF,
        fw_version & 0xFFFFFFFF,
        len(norm),
        crc,
        0,
    )
    return header + bytes(payload)


def decode_patches(blob: bytes) -> PatchPackage:
    """Parse and strictly validate an LMLX PATCHES.BIN byte buffer."""
    if len(blob) < HEADER_STRUCT.size:
        raise PatchValidationError(f"文件过短 ({len(blob)} 字节), 至少需要 {HEADER_STRUCT.size} 字节")

    magic, fmt_ver, flags, fw_ver, count, stored_crc, reserved = HEADER_STRUCT.unpack_from(blob, 0)
    if magic != MAGIC:
        raise PatchValidationError(f"魔数不匹配: 期望 {MAGIC!r}, 实际 {magic!r}")
    if fmt_ver != FORMAT_VER:
        raise PatchValidationError(f"不支持的格式版本: 0x{fmt_ver:04X}")
    if count > MAX_ENTRIES:
        raise PatchValidationError(f"条目数超限: {count} > {MAX_ENTRIES}")
    if reserved != 0:
        raise PatchValidationError(f"保留字段非零: 0x{reserved:08X}")

    expected_len = HEADER_STRUCT.size + count * ENTRY_STRUCT.size
    if len(blob) != expected_len:
        raise PatchValidationError(
            f"文件长度不匹配: 期望 {expected_len} 字节, 实际 {len(blob)} 字节"
        )

    payload = blob[HEADER_STRUCT.size:]
    calc_crc = zlib.crc32(payload) & 0xFFFFFFFF
    if calc_crc != stored_crc:
        raise PatchValidationError(
            f"CRC32 校验失败: 头记录 0x{stored_crc:08X}, 实际计算 0x{calc_crc:08X}"
        )

    entries: List[PatchEntry] = []
    for i in range(count):
        va, orig, new = ENTRY_STRUCT.unpack_from(payload, i * ENTRY_STRUCT.size)
        e = PatchEntry(target_va=va, expected_orig=orig, new_val=new)
        e.validate()
        entries.append(e)

    # Also ensure no conflicting duplicate entries
    validate_entries(entries)

    return PatchPackage(
        fw_version=fw_ver,
        flags=flags,
        entries=tuple(entries),
        format_ver=fmt_ver,
        payload_crc32=stored_crc,
    )


def verify_against_program_bin(
    entries: Sequence[PatchEntry],
    program_bin_path: str | Path,
) -> List[Tuple[PatchEntry, bool, str]]:
    """Offline check: verify each entry's expected_orig against decrypted program.bin."""
    path = Path(program_bin_path)
    if not path.is_file():
        raise FileNotFoundError(f"未找到明文 program.bin: {path}")
    fw_data = path.read_bytes()
    fw_len = len(fw_data)

    results: List[Tuple[PatchEntry, bool, str]] = []
    for raw in entries:
        e = raw.normalized()
        off = e.target_va - MAIN_VA_BASE
        if off < 0 or off + 2 > fw_len:
            results.append(
                (
                    e,
                    True,
                    f"RUNTIME_RAM (偏移 0x{off:X} 超出静态 program.bin 0x{fw_len:X}，由机内运行态原值比对把关)",
                )
            )
            continue
        actual = struct.unpack_from("<H", fw_data, off)[0]
        if actual == e.expected_orig:
            results.append((e, True, f"MATCH (off=0x{off:06X}, orig=0x{actual:04X})"))
        else:
            results.append(
                (
                    e,
                    False,
                    f"MISMATCH (off=0x{off:06X}, 期望 0x{e.expected_orig:04X}, 实际 0x{actual:04X})",
                )
            )
    return results
