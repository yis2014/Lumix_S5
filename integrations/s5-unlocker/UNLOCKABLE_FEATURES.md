# Lumix DC-S5 (`MC801`, FW 2.9) — Unlockable Features Reference

This document catalogs every video/camera feature accessible via the **volatile RTOS RAM**
workflow over Panasonic temporary Service Mode USB (`04DA:2370`, `op 0x9B` read / `op 0x9C` write).

> **Safety & Persistence Model:**
> - **0% flash / EEPROM / bootloader writes** — zero brick risk.
> - **Survives Power-Switch OFF/ON (suspend-to-RAM)** when master ROM-in-RAM templates (`0x8708xxxx`) are patched alongside the active RAM tables (`0x08A6xxxx` / `0x86F1xxxx` / `0x8682xxxx`).
> - **Battery removal (cold boot)** instantly restores 100% factory stock firmware.
> - **Strict target:** Original Lumix DC-S5 (Mark I, `MC801`), stock **Firmware 2.9** only.

---

## 1. Live-Verified & Deployed Today

| Feature | Mode / Address | Specs & Verified Behavior |
| :--- | :--- | :--- |
| **6K 3:2 Open Gate 23.98p MOV** | `qid 0x00ED` | `5952×3968` (full 3:2 sensor), 23.98p, HEVC Main 10 4:2:0 10-bit, 200 Mbps, 48 kHz stereo PCM audio, timecode. Appears natively in **Rec Quality (MOV)**, updates live-view `6K` badge, plays back natively in-camera, **no 30-min cap**. |
| **5.9K 16:9 23.98p MOV** | `qid 0x00F1` | `5888×3312` (full-frame 16:9), 23.98p, HEVC Main 10 4:2:0 10-bit, 200 Mbps. Appears natively in **Rec Quality (MOV)**, updates live-view `5.9K` badge, **no 30-min cap**. |
| **5.9K 16:9 29.97p MOV** | `qid 0x00F4` | `5888×3312`, 29.97p, HEVC Main 10 4:2:0 10-bit, ~194 Mbps (`P1118468.MOV` verified: 231.84 MiB, 10.010 s, 300 frames, PCM audio, timecode, **no 30-min cap**). |
| **Unlimited Recording (All Limited Modes)** | `0x868261B6: 0x4628 → 0x2000` | Removes both the **30-minute (`0x708`)** and **15-minute (`0x384`)** artificial recording caps across all 4K, C4K, 4K-A 10-bit, 60p, and VFR modes. Card capacity and hardware thermal protection remain intact. |
| **Power-Switch Persistence (Suspend-to-RAM)** | `0x87089614`–`0x8708962C` | Patching the master ROM-in-RAM MOV template alongside `0x86F15E30`, `0x08A68B6C`, `0x08A6836C`, and `0x868261B6` keeps all unlocked modes + unlimited recording active across Power-Switch OFF/ON until battery removal. |

### How Native Rec Quality Menu Injection Works
Any MOV quality ID present in the live movie-quality table (`0x08AA45E0`) can be exposed natively
in the NTSC 59.94 Hz MOV Rec Quality menu by swapping unused low-priority FHD slots (e.g. `0x00CC`,
`0x00CE`, `0x00D1`, `0x00D2`) across four RAM structures:
1. **NTSC Validator Whitelist:** `0x86F15E30` (`[qid, 0x8000|qid]` pairs, sentinel `0xFFFF` at `0x86F15E98`)
2. **Master ROM-in-RAM Template:** `0x87089524` (8-byte stride, copied to `0x08A68B6C` on soft wake-up)
3. **Active MOV Source Template:** `0x08A68B6C` (copied to `0x08A6836C` by `0x866930B6` on menu open)
4. **Live UI Menu Buffer:** `0x08A6836C` (validated by `0x86693126`, visibility flag `0x0104` = visible)

---

## 2. Present in Firmware `0x08AA45E0` (Ready to Enable / Live-Test)

These modes already have full entries (codec, resolution, frame rate, bitrate, UI glyphs, and string
IDs) inside the S5's live movie-quality table (`0x08AA45E0`) and can be exposed in the exact same
native menu slots:

### High-Resolution 5.4K / 5.9K / 6K Modes
| Mode | QID | Resolution | Aspect | Frame Rate | Codec / Bitrate | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **6K 3:2 Open Gate 24.00p** | `0x00EE` | `5952×3968` | 3:2 | 24.00p (True 24p) | HEVC 4:2:0 10-bit 200M | Needs quick live record test in 59.94 Hz mode |
| **5.9K 16:9 24.00p** | `0x00F2` | `5888×3312` | 16:9 | 24.00p (True 24p) | HEVC 4:2:0 10-bit 200M | Same 2-core HEVC pipeline as `0x00F1`/`0x00F4` |
| **5.9K 16:9 25.00p (PAL)** | `0x00F3` | `5888×3312` | 16:9 | 25.00p | HEVC 4:2:0 10-bit 200M | For 50.00 Hz PAL system frequency (`0x86F15E9A`) |
| **5.4K 3:2 Open Gate 25.00p** | `0x00EF` | `5376×3584` | 3:2 | 25.00p | HEVC 4:2:0 10-bit 200M | PAL Open Gate; **avoid `0x00F0` (29.97p)** which stalled on record in 59.94 Hz |

### 400 Mbps 10-bit 4:2:2 ALL-Intra MOV Modes
| Mode | QID | Resolution | Frame Rate | Codec / Bitrate | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **4K 23.98p 400M ALL-I** | `0x0098` | `3840×2160` | 23.98p | 4:2:2 10-bit 400M ALL-I | Untested live; requires UHS-II V60/V90 card |
| **C4K 23.98p 400M ALL-I** | `0x00B8` | `4096×2160` | 23.98p | 4:2:2 10-bit 400M ALL-I | Untested live |
| **C4K 29.97p 400M ALL-I** | `0x0090` | `4096×2160` | 29.97p | 4:2:2 10-bit 400M ALL-I | Untested live |
| **4K-A (4:3) 23.98p 400M ALL-I** | `0x00A9` | `3328×2496` | 23.98p | 4:2:2 10-bit 400M ALL-I | Anamorphic 4:3 ALL-Intra; untested live |
| **FHD 23.98p 200M ALL-I** | `0x00D0` | `1920×1080` | 23.98p | 4:2:2 10-bit 200M ALL-I | Untested live |

### Additional C4K & Anamorphic Entries
- **C4K (`4096×2160`) 23.98p 100M 8-bit (`0x00B6`) / 150M 4:2:2 10-bit (`0x00B7`)** directly in 59.94 Hz NTSC without switching System Frequency.
- **3.5K 4:3 Anamorphic (`3536×2656`, APS-C)** (`0x00F5`–`0x00F8`) — present for HDMI RAW; untested internally. *(Note: stock S5 already includes `4K-A 3328×2496 23.98p` as `0x00A7`/`0x00A8`; there is no `4992×3744` MOV entry in `0x08AA45E0`.)*

---

## 3. Experimental / Research Candidates (Same Volatile RAM Method)

These have not been live-tested yet but sit in the same writable RTOS RAM architecture:
- **Custom Bitrate Bump (`0x08AA45E0` field `w5`):** Target Mbps (`200` for 6K/5.9K, `150` for 4K 10-bit) is stored directly in writable RAM. Needs a quick live test to see if the Venus Engine HEVC/H.264 rate-controller honors a raised value (e.g. `200 → 300`).
- **Hidden S1/S1H UI Menu Items (`0x08A6xxxx`):** Any S1/S1H-tier menu option compiled into the shared `MC801` RTOS and merely hidden (`f1 = 0x0101` / `0x0102`) in `0x08A6xxxx` (e.g., Waveform/Vectorscope, extra Anamorphic desqueeze ratios, VFR/HDMI toggles) can be audited and tested by flipping visibility to `0x0104`.
- **PAL 50.00 Hz Menu Table Support:** Mirroring the same 4-table swap on the PAL whitelist (`0x86F15E9A`) and PAL MOV template (`0x08A68C84`) to expose 5.9K 25p (`0x00F3`) and 5.4K 25p (`0x00EF`) natively for PAL shooters.

---

## 4. Hardware-Limited (Cannot Be Unlocked by Software)

- **Full-frame uncropped 4K 60p or 6K 60p:** Limited by the IMX410 24 MP sensor's readout speed (60p requires APS-C crop).
- **Internal ProRes / Internal RAW (BRAW):** No ProRes or RAW hardware encoder on the S5's Venus Engine.
- **Phase-Detect Autofocus (PDAF):** Hardware sensor limitation (S5 uses DFD contrast AF only).
- **Permanent Flash Persistence:** `.UPD` enforces ECDSA P-256 (`0x868C08C6`); `ROM BACKUP` (`0x8785CE42`) is EEPROM-only. Volatile RAM + suspend-to-RAM survival is the safe, zero-brick-risk path.
