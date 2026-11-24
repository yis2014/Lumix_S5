"""Profile registry for LUMIX S5 SD-card modular features."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

from .patch_format import FW_VER_S5_V29, PatchEntry, validate_entries

DEFAULT_PROFILES_FILE = Path(__file__).with_name("profiles_v29.json")


def _parse_int(val: int | str) -> int:
    if isinstance(val, int):
        return val
    return int(str(val).strip(), 0)


@dataclass(frozen=True)
class FeatureProfile:
    id: str
    name: str
    category: str
    risk: str
    status: str
    description: str
    entries: tuple[PatchEntry, ...]
    fw_version: int = FW_VER_S5_V29


def load_profiles(path: str | Path | None = None) -> List[FeatureProfile]:
    """Load feature profiles from JSON file."""
    src = Path(path) if path else DEFAULT_PROFILES_FILE
    raw = json.loads(src.read_text(encoding="utf-8"))
    default_fw = _parse_int(raw.get("fw_version", FW_VER_S5_V29))
    profiles: List[FeatureProfile] = []
    for item in raw.get("profiles", []):
        entries = tuple(
            PatchEntry(
                target_va=_parse_int(e["addr"]),
                expected_orig=_parse_int(e["orig"]),
                new_val=_parse_int(e["new"]),
                note=str(e.get("note", "")),
            ).normalized()
            for e in item.get("entries", [])
        )
        profiles.append(
            FeatureProfile(
                id=str(item["id"]),
                name=str(item["name"]),
                category=str(item.get("category", "未分类")),
                risk=str(item.get("risk", "未知")),
                status=str(item.get("status", "")),
                description=str(item.get("description", "")),
                entries=entries,
                fw_version=_parse_int(item.get("fw_version", default_fw)),
            )
        )
    return profiles


def merge_profiles(profiles: Sequence[FeatureProfile]) -> List[PatchEntry]:
    """Combine and validate entries from multiple selected profiles."""
    combined: List[PatchEntry] = []
    for p in profiles:
        combined.extend(p.entries)
    return validate_entries(combined)
