# DC-S5 关键地址表

| 地址或范围 | 用途 | 关联文件 |
|---|---|---|
| `0x80000000` | Reset 向量和常驻低地址启动代码 | `dumps/lowmem_0_2M.bin` |
| `0x800003C4` | Reset 链主核交接点 | `analysis/低地址Reset加载跳转CFG_20261119.md` |
| `0x80120800` | DTB 副本 | `dumps/dtb_120800.bin` |
| `0x83100000` | rootfs1 加载地址 | `dumps/rootfs1_dump.bin` |
| `0x83400000` | rootfs2 加载地址 | `dumps/rootfs2_dump.bin` |
| `0x86280000` | 主核 program 加载地址 | `dumps/program_0x86280000.bin` |
| `0x868C5E48` | 镜头头部/版本校验冷函数 | `lumix_ml/deploy_validator_detour.py` |
| `0x868C69EC` | 镜头设钥 API | `keys/KEY_MATERIAL_PUBLIC.md` |
| `0x868F9A0C` | 主核入口分支 | `analysis/S5代码执行实证_20261119.md` |
| `0x87086300` | 曾使用的 rodata 代码洞 | 复用前必须读回并恢复 |
| `0x87086A00` | 活动浮点表区 | 禁止写入 |
| `0x8F000100` 起 | 探针和复制缓冲区候选 | Service USB 读回确认 |
| `0x8DC00000`、`0x8DF00000` | OSD 双缓冲 | `lumix_ml/osd_tool.py` |
| `0x7F050000` | PL011 UART | DTB/bootargs 为 `ttyAMA,115200` |
| `0x7C200000` | USB DWC3 | DTB |
| `0x7C300000` | SDHCI | DTB |

## 当前基线字节

- `0x868F9A0C` 原始首字节为 `82 00 00 EA`
- `0x800003C4` 原始首字节为 `D8 F0 9F E5`
- `0x863B0000` 和 `0x863181E2` 官方 V2.9 版本结构为 `90 02 90 02`

## 读写纪律

Service USB 写入使用 `0x9C` 半字操作。每个半字都要读回确认。任何新的硬件动作先读取目标、代码洞、缓冲区和计数器，再决定是否写入。
