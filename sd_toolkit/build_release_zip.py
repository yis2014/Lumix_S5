"""Build a clean, self-contained delivery ZIP for LUMIX S5 SD-Card Modular Toolkit."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from sd_toolkit import __version__

ROOT = Path(__file__).resolve().parent.parent
PKG_PREFIX = f"LUMIX_S5_SD基座工具_v{__version__}"
OUT_ZIP = ROOT / "delivery" / f"{PKG_PREFIX}.zip"

FILES_TO_PACK = [
    (ROOT / "sd_toolkit" / "README_交接与使用说明.md", f"{PKG_PREFIX}/README_交接与使用说明.md"),
    (ROOT / "launch_sd_tool.bat", f"{PKG_PREFIX}/launch_sd_tool.bat"),
    (ROOT / "sd_toolkit" / "__init__.py", f"{PKG_PREFIX}/sd_toolkit/__init__.py"),
    (ROOT / "sd_toolkit" / "patch_format.py", f"{PKG_PREFIX}/sd_toolkit/patch_format.py"),
    (ROOT / "sd_toolkit" / "profiles.py", f"{PKG_PREFIX}/sd_toolkit/profiles.py"),
    (ROOT / "sd_toolkit" / "profiles_v29.json", f"{PKG_PREFIX}/sd_toolkit/profiles_v29.json"),
    (ROOT / "sd_toolkit" / "sd_manager.py", f"{PKG_PREFIX}/sd_toolkit/sd_manager.py"),
    (ROOT / "sd_toolkit" / "cli.py", f"{PKG_PREFIX}/sd_toolkit/cli.py"),
    (ROOT / "sd_toolkit" / "app_gui.py", f"{PKG_PREFIX}/sd_toolkit/app_gui.py"),
    (ROOT / "tests" / "__init__.py", f"{PKG_PREFIX}/tests/__init__.py"),
    (ROOT / "tests" / "test_sd_patch_tool.py", f"{PKG_PREFIX}/tests/test_sd_patch_tool.py"),
]

RUN_TESTS_BAT = (
    "@echo off\r\n"
    'cd /d "%~dp0"\r\n'
    'python -m unittest discover -s tests -p "test_sd_patch_tool.py" -v\r\n'
    "pause\r\n"
)


def main() -> int:
    OUT_ZIP.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for src, arc in FILES_TO_PACK:
            zf.write(src, arc)
        zf.writestr(f"{PKG_PREFIX}/run_tests.bat", RUN_TESTS_BAT.encode("utf-8"))

    print(f"Created: {OUT_ZIP} ({OUT_ZIP.stat().st_size:,} bytes)")
    with zipfile.ZipFile(OUT_ZIP, "r") as zf:
        for info in zf.infolist():
            print(f"  {info.filename:65s} {info.file_size:6d}B")

    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(OUT_ZIP, "r") as zf:
            zf.extractall(tmp)
        extracted = Path(tmp) / PKG_PREFIX
        res = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_sd_patch_tool.py", "-v"],
            cwd=str(extracted),
            capture_output=True,
            text=True,
        )
        print("\n--- Standalone Zip Verification ---")
        print(res.stderr.strip())
        if res.returncode != 0:
            print(res.stdout)
            return res.returncode
    print("STANDALONE ZIP TEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
