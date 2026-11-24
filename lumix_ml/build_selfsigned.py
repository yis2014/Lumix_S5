#!/usr/bin/env python3
"""Build a self-signed, version-bumped, CRC-consistent S5 firmware package.

Full correct pipeline (order matters):
  1. bump version at 0x1c and 0x2bc   (0x1c outside digest; 0x2bc inside)
  2. recompute digest  SHA256(fw[0x2A0:0x142C])
  3. self-sign with OUR private key  (r||s little-endian -> 0x220:0x260)
  4. recompute CRC32  zlib.crc32(fw[0x200:]) -> 0x40

Usage:
  python lumix_ml/build_selfsigned.py --src firmware/S5___V29.bin --out S5___V29_selfsigned_2a0.bin
  python lumix_ml/build_selfsigned.py verify --out S5___V29_selfsigned_2a0.bin
"""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import struct
import sys
import zlib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ecdsa_recover import P256, mul, verify as ec_verify  # noqa: E402

DEFAULT_SRC = REPO_ROOT / "firmware" / "S5___V29.bin"
DEFAULT_OUT = REPO_ROOT / "S5___V29_selfsigned_2a0.bin"
DEFAULT_KEYPAIR = REPO_ROOT / "keys" / "local_keypair.json"
FALLBACK_KEYPAIR = REPO_ROOT / "analysis" / "vectors" / "ecdsa" / "p256_ref_keypair.json"
DEFAULT_VERSION = 0x02A002A0  # 2.160 (> 2.90)


def _resolve_keypair(keypair_path: Path) -> Path:
    if not keypair_path.is_file() and keypair_path == DEFAULT_KEYPAIR and FALLBACK_KEYPAIR.is_file():
        return FALLBACK_KEYPAIR
    return keypair_path


def build(src: Path, out: Path, keypair_path: Path, version: int) -> None:
    fw = bytearray(src.read_bytes())

    # 1. version bump
    struct.pack_into("<I", fw, 0x1C, version)
    struct.pack_into("<I", fw, 0x2BC, version)

    # 2. digest
    digest = hashlib.sha256(bytes(fw[0x2A0:0x142C])).digest()
    e = int.from_bytes(digest, "little")

    # 3. self-sign
    kp = json.loads(_resolve_keypair(keypair_path).read_text(encoding="utf-8"))
    priv = int(kp["private"], 16)
    n = P256.n
    while True:
        k = secrets.randbelow(n - 1) + 1
        r_pt = mul(P256, k, P256.G)
        r = r_pt[0] % n
        if r == 0:
            continue
        s = (pow(k, -1, n) * (e + r * priv)) % n
        if s == 0:
            continue
        break
    sig = r.to_bytes(32, "little") + s.to_bytes(32, "little")
    fw[0x220:0x260] = sig

    # 4. CRC32 over fw[0x200:]
    crc = zlib.crc32(bytes(fw[0x200:])) & 0xFFFFFFFF
    struct.pack_into("<I", fw, 0x40, crc)

    out.write_bytes(bytes(fw))
    print(f"built -> {out}")
    print(f"  version 0x1c/0x2bc = {version:#010x}")
    print(f"  digest = {digest.hex()}")
    print(f"  r = {r:x}")
    print(f"  s = {s:x}")
    print(f"  crc32 = {crc:#010x}")
    verify_file(out, keypair_path, version)


def verify_file(path: Path, keypair_path: Path, expected_version: int) -> bool:
    fw = path.read_bytes()
    kp = json.loads(_resolve_keypair(keypair_path).read_text(encoding="utf-8"))
    q = (int(kp["public_x"], 16), int(kp["public_y"], 16))

    v1 = struct.unpack_from("<I", fw, 0x1C)[0]
    v2 = struct.unpack_from("<I", fw, 0x2BC)[0]
    digest = hashlib.sha256(fw[0x2A0:0x142C]).digest()
    e = int.from_bytes(digest, "little")
    r = int.from_bytes(fw[0x220:0x260][:32], "little")
    s = int.from_bytes(fw[0x220:0x260][32:], "little")
    crc_stored = struct.unpack_from("<I", fw, 0x40)[0]
    crc_calc = zlib.crc32(fw[0x200:]) & 0xFFFFFFFF

    ok_sig = ec_verify(P256, q, r, s, e)
    ok_crc = crc_stored == crc_calc
    ok_ver = v1 == expected_version and v2 == expected_version

    print("VERIFY:")
    print(f"  version ok   : {ok_ver} ({v1:#x}/{v2:#x})")
    print(f"  signature ok : {ok_sig}")
    print(f"  crc32 ok     : {ok_crc}")
    print(f"  ALL OK       : {ok_sig and ok_crc and ok_ver}")
    return ok_sig and ok_crc and ok_ver


def main() -> None:
    parser = argparse.ArgumentParser(description="Build & verify self-signed DC-S5 firmware package")
    parser.add_argument("action", nargs="?", default="build", choices=["build", "verify"])
    parser.add_argument("--src", default=str(DEFAULT_SRC), help="Input official firmware .bin")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output self-signed firmware .bin")
    parser.add_argument("--keypair", default=str(DEFAULT_KEYPAIR), help="Local P-256 keypair JSON")
    parser.add_argument("--version", default=hex(DEFAULT_VERSION), help="Target version u32 (e.g. 0x02A002A0)")
    args = parser.parse_args()

    version = int(args.version, 0)
    if args.action == "verify":
        ok = verify_file(Path(args.out), Path(args.keypair), version)
        raise SystemExit(0 if ok else 1)
    build(Path(args.src), Path(args.out), Path(args.keypair), version)


if __name__ == "__main__":
    main()
