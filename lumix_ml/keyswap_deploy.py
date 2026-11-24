#!/usr/bin/env python3
"""Key-swap: replace the firmware's ECDSA trust anchor with OUR public key.

This is the clean "own the signature" route. Instead of disabling signature
checking, we swap the stored public key (K2/K3 in the cert table) for our own
P-256 public key, so only packages signed with OUR private key will verify.

Two stages:
  1. RAM-level swap (this script) -- zero-risk, reversible, proves the math
     and the trust-anchor identity. Does NOT touch flash.
  2. Persistent swap (planned) -- edit program.bin plaintext K2 @ 0xcd3722
     + 5-round AES-128-CBC re-encrypt + repack + self-sign + flash.

Usage:
  python lumix_ml/keyswap_deploy.py keygen     # generate a fresh local P-256 keypair
  python lumix_ml/keyswap_deploy.py selftest   # offline: verify keypair & RAM layout
  python lumix_ml/keyswap_deploy.py status     # read current K2/K3 in RAM (no write)
  python lumix_ml/keyswap_deploy.py deploy     # swap K2+K3 RAM pubkeys to ours (with backup)
  python lumix_ml/keyswap_deploy.py rollback   # restore original K2/K3 from backup
  python lumix_ml/keyswap_deploy.py selfsign   # sign firmware/S5___V29.bin with our key
"""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ecdsa_recover import P256, mul, verify as ec_verify  # noqa: E402

DEFAULT_KEYPAIR = REPO_ROOT / "keys" / "local_keypair.json"
DEFAULT_BACKUP = REPO_ROOT / "keyswap_backup.json"
DEFAULT_FW_SRC = REPO_ROOT / "firmware" / "S5___V29.bin"
DEFAULT_FW_OUT = REPO_ROOT / "S5___V29_selfsigned.bin"

K2_ADDR = 0x86F53722
K3_ADDR = 0x86F537C0

# Original K2 raw bytes (from S5 V2.9 firmware plaintext / live RAM, confirmed).
ORIG_K2 = bytes.fromhex(
    "9ed24846e6edf035766bb28d0210320929d819ba33d6e3db"
    "a8a745a89159671fcc531522c5ab8f23a6548fe0e4ca7745"
    "23a196e9df58572699da0d78b8ea6891"
)


def our_pubkey_ram(kp: dict) -> bytes:
    x = int(kp["public_x"], 16)
    y = int(kp["public_y"], 16)
    return x.to_bytes(32, "big")[::-1] + y.to_bytes(32, "big")[::-1]


def load_keypair(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(
            f"Keypair not found: {path}\n"
            f"Run `python lumix_ml/keyswap_deploy.py keygen` first to generate a local P-256 keypair."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_keygen(args: argparse.Namespace) -> None:
    out = Path(args.keypair)
    if out.exists() and not args.force:
        raise SystemExit(f"Keypair already exists: {out} (use --force to overwrite)")
    priv = secrets.randbelow(P256.n - 1) + 1
    qx, qy = mul(P256, priv, P256.G)
    kp = {
        "curve": "P-256",
        "private": f"{priv:064x}",
        "public_x": f"{qx:064x}",
        "public_y": f"{qy:064x}",
    }
    kp["ram_pubkey_hex"] = our_pubkey_ram(kp).hex()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(kp, indent=2) + "\n", encoding="utf-8")
    print(f"keygen PASS -> {out}")
    print(f"  pub x   : {kp['public_x']}")
    print(f"  pub y   : {kp['public_y']}")
    print(f"  RAM pub : {kp['ram_pubkey_hex']}")
    print("  NOTE: Keep this file local; local_keypair.json is git-ignored.")


def cmd_selftest(args: argparse.Namespace) -> None:
    kp = load_keypair(Path(args.keypair))
    priv = int(kp["private"], 16)
    q = mul(P256, priv, P256.G)
    assert q == (int(kp["public_x"], 16), int(kp["public_y"], 16)), "pubkey mismatch"
    ram = our_pubkey_ram(kp)
    if "ram_pubkey_hex" in kp:
        assert ram.hex() == kp["ram_pubkey_hex"], "RAM layout mismatch"
    print("selftest PASS: priv*G == pubkey, RAM layout correct")
    print("  pub x   :", kp["public_x"])
    print("  pub y   :", kp["public_y"])
    print("  RAM pub :", ram.hex())


def cmd_selfsign(args: argparse.Namespace) -> None:
    """Re-sign a firmware container with OUR private key (without version bump)."""
    kp = load_keypair(Path(args.keypair))
    priv = int(kp["private"], 16)
    n = P256.n

    src = Path(args.src)
    dst = Path(args.out)
    fw = bytearray(src.read_bytes())

    digest = hashlib.sha256(bytes(fw[0x2A0:0x142C])).digest()
    e = int.from_bytes(digest, "little")

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

    q = (int(kp["public_x"], 16), int(kp["public_y"], 16))
    assert ec_verify(P256, q, r, s, e), "self-sign verify failed"

    dst.write_bytes(bytes(fw))
    print(f"selfsign PASS -> {dst}")
    print(f"  digest(LE) = {digest.hex()}")
    print(f"  r = {r:x}")
    print(f"  s = {s:x}")


def _connect():
    from usb_link import LumixServiceUSB, find_dcs5_device_paths

    for p in find_dcs5_device_paths():
        try:
            return LumixServiceUSB(path=p)
        except Exception:
            continue
    raise SystemExit("device not reachable (is DC-S5 in Service Mode 04DA:2370?)")


def cmd_status(args: argparse.Namespace) -> None:
    u = _connect()
    try:
        k2 = u.read_mem(K2_ADDR, 64)
        k3 = u.read_mem(K3_ADDR, 64)
        kp_path = Path(args.keypair)
        ours = our_pubkey_ram(load_keypair(kp_path)) if kp_path.is_file() else None
        k2_tag = "OURS" if (ours and k2 == ours) else "ORIG" if k2 == ORIG_K2 else "UNKNOWN"
        k3_tag = "OURS" if (ours and k3 == ours) else "ORIG/other"
        print(f"K2 @{K2_ADDR:#x}: {k2_tag}")
        print("  ", k2.hex())
        print(f"K3 @{K3_ADDR:#x}: {k3_tag}")
        print("  ", k3.hex())
    finally:
        u.close()


def cmd_deploy(args: argparse.Namespace) -> None:
    u = _connect()
    try:
        kp = load_keypair(Path(args.keypair))
        ours = our_pubkey_ram(kp)

        k2 = u.read_mem(K2_ADDR, 64)
        k3 = u.read_mem(K3_ADDR, 64)
        if k2 != ORIG_K2:
            raise SystemExit(f"K2 not original (got {k2.hex()[:16]}...), aborting")

        backup_path = Path(args.backup)
        rec = {
            "timestamp": time.time(),
            "K2": {"addr": hex(K2_ADDR), "orig_hex": k2.hex(), "new_hex": ours.hex()},
            "K3": {"addr": hex(K3_ADDR), "orig_hex": k3.hex(), "new_hex": ours.hex()},
        }
        backup_path.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")

        u.write_mem_safe(K2_ADDR, ours)
        u.write_mem_safe(K3_ADDR, ours)

        rb2 = u.read_mem(K2_ADDR, 64)
        rb3 = u.read_mem(K3_ADDR, 64)
        print("K2 swapped ->", "OK" if rb2 == ours else "MISMATCH")
        print("K3 swapped ->", "OK" if rb3 == ours else "MISMATCH")
        print(f"backup saved -> {backup_path}")
    finally:
        u.close()


def cmd_rollback(args: argparse.Namespace) -> None:
    u = _connect()
    try:
        rec = json.loads(Path(args.backup).read_text(encoding="utf-8"))
        for name in ("K2", "K3"):
            addr = int(rec[name]["addr"], 16)
            orig = bytes.fromhex(rec[name]["orig_hex"])
            u.write_mem_safe(addr, orig)
            rb = u.read_mem(addr, 64)
            print(f"{name} restored ->", "OK" if rb == orig else "MISMATCH")
    finally:
        u.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="DC-S5 ECDSA trust-anchor RAM keyswap tool")
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        choices=["keygen", "selftest", "status", "deploy", "rollback", "selfsign"],
    )
    parser.add_argument("--keypair", default=str(DEFAULT_KEYPAIR), help="Path to local P-256 keypair JSON")
    parser.add_argument("--backup", default=str(DEFAULT_BACKUP), help="Path to RAM backup JSON")
    parser.add_argument("--src", default=str(DEFAULT_FW_SRC), help="Input firmware .bin (for selfsign)")
    parser.add_argument("--out", default=str(DEFAULT_FW_OUT), help="Output firmware .bin (for selfsign)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing keypair on keygen")
    args = parser.parse_args()

    dispatch = {
        "keygen": cmd_keygen,
        "selftest": cmd_selftest,
        "status": cmd_status,
        "deploy": cmd_deploy,
        "rollback": cmd_rollback,
        "selfsign": cmd_selfsign,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
