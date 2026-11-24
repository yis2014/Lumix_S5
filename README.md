# LUMIX DC-S5 (`MC801` / `pvc03v`, FW 2.9) 综合固件研究与工具箱

本项目整合了 **三个互补的 Panasonic LUMIX DC-S5（Mark I, FW 2.9）开源研究与工具生态**，将「零刷机 RAM 即时解锁」「Windows 桌面端驱动/音效/诊断工具箱」与「Own the Signature 换公钥自签 + SD 卡模块化基座」统一到同一仓库中：

1. **本项目核心路线（密钥、自签固件与 SD 卡基座）**：
   - **5 轮 AES-128-CBC 全 47 分区解密**（`lumix_ml/decrypt_all.py`）
   - **Own the Signature（换公钥自签）**：RAM 替换 ECDSA P-256 验签信任锚 `K2@0x86F53722` + `K3@0x86F537C0` 并用本地私钥自签固件（`lumix_ml/keyswap_deploy.py`、`lumix_ml/build_selfsigned.py`），已在真机验证通过机身验签函数 `0x868C08C6`
   - **Magic Lantern 启动链钩取 & 任意载荷**：`lumix_ml/boot_exec.py`（`0x800003C4` detour → `0x8000E300`）、`lumix_ml/arb_exec.py`（`0x87086300`）
   - **SD 卡模块化基座工具（`sd_toolkit/`）**：零第三方依赖 GUI/CLI，生成与校验 `SD:\LUMIX_ML\PATCHES.BIN`（`LMLX` 协议 + CRC32 + 禁写区护栏），面向「一次最小化引导激活 + 后续永久免 USB、纯 SD 卡管理功能，拔卡即 100% 原厂」的终极形态
2. **整合 [`rileydeacon/s5-unlocker`](https://github.com/rileydeacon/s5-unlocker)（MIT）**：
   - 真机已验证的 **19 半字纯 RAM 补丁**（0 刷写、0 变砖风险、支持电源键热重启持久化、拔电池即还原）：在原生 `Rec Quality (MOV)` 菜单解锁 **6K 3:2 Open Gate (`0x00ED`, `5952×3968` 23.98p)**、**5.9K 16:9 (`0x00F1`, `5888×3312` 23.98p)** 与 **全模式无限录制（`0x868261B6: 0x4628 → 0x2000`）**
   - 完整保留 **WebUSB 一键网页端**（`integrations/s5-unlocker/docs/index.html`）、**Android 离线 OTG App**（`integrations/s5-unlocker/android/`）与 **macOS CLI**（`integrations/s5-unlocker/mac-cli/`）
   - 其 19 半字实测补丁已同步合入 `sd_toolkit/profiles_v29.json`，可直接通过 `sd_toolkit` 打包生成 `PATCHES.BIN`
3. **整合 [`USER-HFC/Lumix_Tool`](https://github.com/USER-HFC/Lumix_Tool)**：
   - **Windows 桌面应用**（Electron + React + Ant Design + Python 后端，位于 `integrations/lumix-tool/app/`）：一键安装 `04DA:2370` WinUSB 驱动、只读 RAM 暂存区分布图诊断、28 项相机提示音/快门音效自定义替换（`0x8F000000` 暂存区）
   - 配套固件容器解析、免密钥 `flags=2` 重打包、`0x8631801A` 验签开关恢复脚本与 OSD/squashfs 研究工具（位于 `integrations/lumix-tool/tools/`、`js/`、`docs/`）

> 详细的技术路线融合、信任链对照与持久化阶梯设计，请参阅 **[INTEGRATION_ARCHITECTURE.md](INTEGRATION_ARCHITECTURE.md)**。

---

## 仓库目录结构

| 目录 / 文件 | 说明 |
|---|---|
| [`INTEGRATION_ARCHITECTURE.md`](INTEGRATION_ARCHITECTURE.md) | **三项目技术整合架构**：换公钥自签、免密钥 `flags=2`、RAM 解锁与 SD 卡基座的完整对照与协同路线 |
| [`HANDOFF.md`](HANDOFF.md) | 最新项目交接文档（换公钥实证、打包顺序、QEMU `panasonic-pvc03v` 进展） |
| [`HANDOFF_LUMIX_S5_20261119.md`](HANDOFF_LUMIX_S5_20261119.md) | 早期研究交接归档 |
| [`ADDRESS_TABLE.md`](ADDRESS_TABLE.md) | DC-S5 V2.9 关键内存地址与范围速查表 |
| [`sd_toolkit/`](sd_toolkit/) | PC 端零依赖 SD 卡模块化基座工具（GUI/CLI、`LMLX` 协议、已内置 `s5-unlocker` 实测档案） |
| [`tests/`](tests/) | `sd_toolkit` 自动化离线单元测试（含对 V2.9 `program.bin` 原厂半字的自动校验） |
| [`lumix_ml/`](lumix_ml/) | 本项目核心工具：`keyswap_deploy.py`、`build_selfsigned.py`、`ecdsa_recover.py`、`boot_exec.py`、`arb_exec.py`、`decrypt_all.py`、`ram_only_observer.py` 等 |
| [`integrations/s5-unlocker/`](integrations/s5-unlocker/) | 源自 `rileydeacon/s5-unlocker`（MIT）：WebUSB、Android OTG App、macOS CLI 与可解锁模式清单 |
| [`integrations/lumix-tool/`](integrations/lumix-tool/) | 源自 `USER-HFC/Lumix_Tool`：Electron 桌面音效/内存诊断/驱动安装工具箱及 `tools/` 研究脚本（已排除 5.3 MB `zadig.exe`，请从官网获取） |
| [`analysis/`](analysis/) | 静态分析结论、CFG、转储差分与验签分析记录 |
| [`firmware/`](firmware/) / [`dumps/`](dumps/) / [`keys/`](keys/) | 官方 V2.9 基线（Git LFS）、必要窗口转储与公开公钥（**不含任何私钥**） |

---

## 快速开始

### 1. 零风险即时解锁 6K Open Gate / 5.9K / 无限录制（RAM 级）
- **浏览器（Chrome WebUSB）**：打开 `integrations/s5-unlocker/docs/index.html`（或访问上游托管页），相机按住 `PLAYBACK + AF/AE LOCK` 开机进入服务模式（`04DA:2370`），连接 USB-C 一键解锁。
- **Android 手机**：使用 `integrations/s5-unlocker/android/` 构建离线 APK，USB-C OTG 即插即解锁。
- **Windows 驱动问题**：使用 `integrations/lumix-tool/app/` 内置的一键 WinUSB 驱动安装向导，或参阅 `integrations/lumix-tool/docs/DRIVER_SETUP.md`。

### 2. 自定义相机提示音 / 内存诊断（Windows 桌面应用）
```bash
cd integrations/lumix-tool/app
npm ci
npm start              # 启动桌面应用（无相机可用 LUMIXTOOL_MOCK=1 npm start）
```

### 3. SD 卡模块化基座工具（PC 端管理 `PATCHES.BIN`）
```powershell
# 启动图形界面（零第三方依赖）
python -m sd_toolkit.app_gui

# 命令行：列出内置档案（含 s5-unlocker 6K/5.9K 原生菜单 + 无限录制）
python -m sd_toolkit.cli list-profiles

# 部署指定功能到 SD 卡（自动备份旧文件）
python -m sd_toolkit.cli deploy H:\ --profile s5_v29_native_6k_59k_menu --profile s5_v29_unlimited_rec

# 运行离线单元测试
python -m unittest discover -s tests -p "test_sd_patch_tool.py" -v
```

### 4. Own the Signature：本地生成密钥对、RAM 换公钥与自签固件
```powershell
# 1) 本地生成 P-256 密钥对（自动写入 keys/local_keypair.json，已被 .gitignore 忽略）
python lumix_ml/keyswap_deploy.py keygen
python lumix_ml/keyswap_deploy.py selftest

# 2) 构建自签、版本号递增、CRC32 一致的测试固件包
python lumix_ml/build_selfsigned.py --src firmware/S5___V29.bin --out S5___V29_selfsigned_2a0.bin

# 3) 连接服务模式相机：查看状态 / RAM 级换公钥 / 回滚原厂公钥
python lumix_ml/keyswap_deploy.py status
python lumix_ml/keyswap_deploy.py deploy
python lumix_ml/keyswap_deploy.py rollback
```

> **安全边界提示**：
> - `integrations/s5-unlocker` 与 `integrations/lumix-tool/app` 默认**只写易失性 RAM**，0 刷写、拔电池即恢复原厂。
> - `lumix_ml/keyswap_deploy.py deploy` 同样仅修改 RAM 中 `K2`/`K3` 公钥；**只有当您主动将自签/重打包固件放到 SD 卡并通过相机菜单触发刷机时，才会写入 Flash**。在尝试任何持久化写 Flash 前，务必先完成官方 `S5___V29.bin` 回滚演练。

---

## 致谢与协议

- 本项目整合了以下优秀社区项目的源码与研究成果，特此致谢：
  - [`rileydeacon/s5-unlocker`](https://github.com/rileydeacon/s5-unlocker) — MIT License（完整保留于 `integrations/s5-unlocker/LICENSE`）
  - [`USER-HFC/Lumix_Tool`](https://github.com/USER-HFC/Lumix_Tool) — 完整保留原始说明与文档于 `integrations/lumix-tool/`
- 本项目与 Panasonic 无任何关联。服务模式、内存改写与自签固件均不在官方支持范围内，使用风险自负。
- 完整原始大文件归档仍保存在 `full-archive-20261119` 标签中，大文件通过 Git LFS 管理。
