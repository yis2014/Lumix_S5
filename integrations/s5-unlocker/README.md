# Lumix DC-S5 (`MC801`, FW 2.9) — Native 6K Open Gate, 5.9K & Unlimited Recording

Unlock **native-menu internal 6K 3:2 Open Gate (`5952×3968` 23.98p)**, **5.9K 16:9 (`5888×3312` 23.98p)**, and **unlimited recording in all limited modes** on the original **Panasonic Lumix DC-S5 (Mark I)** — with **zero flash writes, zero soldering, and 0% brick risk**.

- **Native S5 UI:** Both `6K 3:2 23.98p` (`0x00ED`) and `5.9K 16:9 23.98p` (`0x00F1`) appear directly at the bottom of **Menu → Video → Rec Quality (MOV)** with native live-view badges (`6K` / `5.9K`) and free switching with stock 4K/FHD modes.
- **Unlimited Recording:** Removes both the 30-minute and 15-minute artificial caps across all 4K, C4K, 4K-A 10-bit, 60p, and VFR modes (card capacity and hardware thermal protection stay intact).
- **Survives Power-Switch OFF/ON:** Stays active across normal power-switch cycles via DRAM self-refresh until you open the battery door or pull the battery.
- **100% Reversible (0% Brick Risk):** Writes only 19 volatile RAM halfwords after verifying 13 firmware signature anchors. Pulling the battery restores 100% factory stock instantly.

> [!CAUTION]
> **Supported hardware & firmware ONLY:** Original **Lumix DC-S5 (Mark I, `MC801`) running stock Firmware 2.9**.
> Both the Android app and WebUSB page verify **13 firmware signature anchors** before writing a single byte and will safely abort on any other camera or firmware version. No warranty; use at your own risk.

---

## Quick Start (Choose One)

### Option 1 — Offline Android App (`S5Unlocker.apk`, Recommended for Field Use)
Works on any USB-C Android phone with USB OTG (**zero Wi-Fi, zero browser**, auto-launches on plug-in):
1. Download `S5Unlocker.apk` from **Releases** (or build from [`android/`](android/)) and install it on your Android phone.
2. On the DC-S5, hold **PLAYBACK + AF/AE LOCK** and flip Power **ON** (temporary service mode `04DA:2370`).
3. Plug a USB-C cable between the phone and S5 — **S5 Unlocker** pops up automatically.
4. Tap **Unlock camera**, wait ~1 second for **Armed**, and unplug the cable.
5. Open **Menu → Video → Rec Quality (MOV)** and scroll to the bottom for **5.9K** and **6K Open Gate**!

### Option 2 — 1-Click Chrome WebUSB (Mac / Windows / Android)
Open the live hosted page at **https://rileydeacon.github.io/s5-unlocker/** (from [`docs/index.html`](docs/index.html)) in **Google Chrome**:
1. Boot the DC-S5 holding **PLAYBACK + AF/AE LOCK** + Power **ON**.
2. Plug USB-C into your Mac, PC, or Android phone.
3. Click **Connect DC-S5** → **Unlock Native Menu + Unlimited Rec** → unplug and shoot.
*(Note: iOS / iPadOS Safari does not support WebUSB.)*

### Option 3 — macOS Command-Line Tool
Build and run [`mac-cli/s5_59k_branch.c`](mac-cli/s5_59k_branch.c) with `clang -O2 -framework IOKit -framework CoreFoundation mac-cli/s5_59k_branch.c -o s5_59k_branch`.

---

## How It Works (MC801 FW 2.9 Volatile RAM Map)

The DC-S5's Venus Engine already contains the 2-core HEVC tile-split encoder (`3072+2880` for `5952×3968`; `2944+2944` for `5888×3312`), the live movie-quality table (`0x08AA45E0`), and the built-in `6K` / `5.9K` UI glyphs & strings. The tool swaps the two lowest FHD MOV slots (`0x00D1` / `0x00D2`) for `0x00F1` / `0x00ED` across all four RTOS menu tables and bypasses the recording-limit return value in `0x86826102`:

| Structure | Address | Unlock → Stock | Purpose |
| :--- | :--- | :--- | :--- |
| NTSC Validator Whitelist | `0x86F15E90`–`96` | `00F1/80F1/00ED/80ED` → `00D1/80D1/00D2/80D2` | Allows `0x00F1` & `0x00ED` in `0x864629B2` |
| Master ROM-in-RAM Template | `0x87089614`–`2C` | `00F1/80F1/00ED/80ED` → `00D1/80D1/00D2/80D2` | Survives soft Power-Switch OFF/ON wake-up |
| Active MOV Source Template | `0x08A68C5C`–`74` | `00F1/80F1/00ED/80ED` → `00D1/80D1/00D2/80D2` | Copied into live UI buffer by `0x866930B6` |
| Live UI Menu Buffer | `0x08A6845C`–`74` | `00F1/0104/80F1/00ED/0104/80ED` | Immediate native Rec Quality UI visibility |
| Recording Limit Getter | `0x868261B6` | `0x2000` (`movs r0, #0`) → `0x4628` | Removes 30-min & 15-min caps across all modes |

---

## Thermal, Battery & Troubleshooting Notes
- **Hardware thermal protection remains active.** Long 6K/4K takes in hot environments will still display normal thermal warnings if the body overheats.
- **Power-switch persistence:** Charging in-body over USB-C (without opening the battery door) or hot-swapping via the **DMW-BGS5 battery grip** keeps DRAM self-refreshed across shoots. Opening the battery door or pulling the battery forces a cold boot back to 100% stock.
- **After pulling the battery while in 6K/5.9K:** If you pull the battery while 6K or 5.9K is still selected, stock FW 2.9 will fall back to `4K 60p 10-bit` (`0x008B`) and the main Rec Quality menu may look limited until refreshed. Just press **Q** once and select any stock Rec Quality (or switch to a stock mode before pulling the battery) to immediately restore the full stock list.

## Disclaimer & License
**Unofficial community project — not affiliated with, endorsed by, or sponsored by Panasonic.** Provided as-is with no warranty; use at your own risk.

MIT License — see [`LICENSE`](LICENSE). Contains 100% original host code and memory offsets only; no Panasonic firmware binaries or copyrighted assets are included.
