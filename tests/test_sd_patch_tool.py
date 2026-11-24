"""Offline unit tests for sd_toolkit (LMLX PATCHES.BIN, safety checks, SD manager, CLI)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sd_toolkit.cli import main as cli_main
from sd_toolkit.patch_format import (
    FW_VER_S5_V29,
    PatchEntry,
    PatchValidationError,
    decode_patches,
    encode_patches,
    normalize_to_main_va,
    verify_against_program_bin,
)
from sd_toolkit.profiles import load_profiles, merge_profiles
from sd_toolkit.sd_manager import deploy_to_sd, inspect_sd, revert_sd

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
PROGRAM_BIN_CANDIDATES = [
    WORKSPACE_ROOT / "analysis" / "decrypted_S5___V29" / "program.bin",
    WORKSPACE_ROOT.parent / "analysis" / "decrypted_S5___V29" / "program.bin",
]
PROGRAM_BIN = next((p for p in PROGRAM_BIN_CANDIDATES if p.is_file()), PROGRAM_BIN_CANDIDATES[0])


class TestPatchFormat(unittest.TestCase):
    def test_roundtrip_and_service_alias_normalization(self) -> None:
        entries = [
            PatchEntry(0x86E3DB1C, 0x0002, 0x0000, "res"),
            PatchEntry(0x074FEF5C, 0x2F32, 0x2F33, "badge"),
        ]
        blob = encode_patches(entries)
        self.assertEqual(len(blob), 24 + 2 * 8)
        pkg = decode_patches(blob)
        self.assertEqual(pkg.fw_version, FW_VER_S5_V29)
        self.assertEqual(len(pkg.entries), 2)
        self.assertEqual(pkg.entries[0].target_va, 0x06E3DB1C)
        self.assertEqual(pkg.entries[1].new_val, 0x2F33)

    def test_crc_corruption_rejected(self) -> None:
        blob = bytearray(encode_patches([PatchEntry(0x06E3DB1C, 0x0002, 0x0000)]))
        blob[-1] ^= 0x01
        with self.assertRaises(PatchValidationError):
            decode_patches(bytes(blob))

    def test_forbidden_and_blackhole_addresses_rejected(self) -> None:
        for bad_addr in (0x07086400, 0x87086A00, 0x068F9A0C, 0x0C000000, 0x06E3DB1D):
            with self.assertRaises(PatchValidationError):
                encode_patches([PatchEntry(bad_addr, 0x0000, 0x0001)])

    def test_conflicting_duplicates_rejected(self) -> None:
        with self.assertRaises(PatchValidationError):
            encode_patches([
                PatchEntry(0x06E3DB1C, 0x0002, 0x0000),
                PatchEntry(0x86E3DB1C, 0x0002, 0x0001),
            ])

    def test_identical_duplicates_deduplicated(self) -> None:
        blob = encode_patches([
            PatchEntry(0x06E3DB1C, 0x0002, 0x0000),
            PatchEntry(0x86E3DB1C, 0x0002, 0x0000),
        ])
        pkg = decode_patches(blob)
        self.assertEqual(len(pkg.entries), 1)
        self.assertEqual(normalize_to_main_va(0x86E3DB1C), 0x06E3DB1C)


class TestProfilesAndRealProgramBin(unittest.TestCase):
    def test_builtin_profiles_merge_and_match_decrypted_v29_program_bin(self) -> None:
        profiles = load_profiles()
        self.assertGreaterEqual(len(profiles), 3)
        entries = merge_profiles(profiles)
        self.assertEqual(len(entries), 24)
        if not PROGRAM_BIN.is_file():
            self.skipTest(f"Decrypted program.bin not found at {PROGRAM_BIN}")
        results = verify_against_program_bin(entries, PROGRAM_BIN)
        self.assertEqual(len(results), 24)
        for e, ok, msg in results:
            self.assertTrue(ok, f"Mismatch at 0x{e.target_va:08X}: {msg}")


class TestSDManagerAndCLI(unittest.TestCase):
    def test_deploy_inspect_backup_revert_flow(self) -> None:
        profiles = load_profiles()
        expected_entries = len(merge_profiles(profiles))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # First deploy
            res1 = deploy_to_sd(root, profiles)
            self.assertEqual(res1["bytes_written"], 24 + expected_entries * 8)
            self.assertIsNone(res1["backup_path"])

            info = inspect_sd(root)
            self.assertTrue(info["patches_exists"])
            self.assertIsNone(info["error"])
            self.assertEqual(len(info["package"].entries), expected_entries)

            # Second deploy creates backup
            res2 = deploy_to_sd(root, profiles)
            self.assertIsNotNone(res2["backup_path"])
            self.assertTrue(Path(res2["backup_path"]).is_file())

            # Revert removes PATCHES.BIN
            rev = revert_sd(root)
            self.assertTrue(rev["removed"])
            info_after = inspect_sd(root)
            self.assertFalse(info_after["patches_exists"])

    def test_cli_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cli_main(["list-profiles"]), 0)
            if PROGRAM_BIN.is_file():
                self.assertEqual(cli_main(["verify-fw", "--program-bin", str(PROGRAM_BIN)]), 0)
            self.assertEqual(
                cli_main(["deploy", tmp, "--profile", "s5_v29_native_6k_59k_menu", "--profile", "s5_v29_unlimited_rec"]),
                0,
            )
            self.assertEqual(cli_main(["inspect", tmp]), 0)
            self.assertEqual(cli_main(["revert", tmp]), 0)


if __name__ == "__main__":
    unittest.main()
