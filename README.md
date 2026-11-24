# LUMIX DC-S5 (`MC801` / `pvc03v`, FW 2.9) 固件研究与模块化工具箱

> [!CAUTION]
> **免责声明与法律风险提示**：本项目仅为面向个人自有设备的嵌入式系统学习与安全研究记录，与 Panasonic（松下）无任何关联。服务模式读写内存、自签固件及非官方修改均存在**设备异常、保修失效甚至变砖风险**，使用风险完全由使用者自行承担。使用前请务必阅读完整的 **[DISCLAIMER.md（免责声明与法律风险提示）](DISCLAIMER.md)**。

本项目汇总了针对 Panasonic LUMIX DC-S5（Mark I, `MC801` / `pvc03v`, FW 2.9）的完整固件分析、密码学验签研究与模块化工具链，覆盖以下三个技术层级：

1. **核心密钥、自签固件与 SD 卡基座路线**：
   - **5 轮 AES-128-CBC 全 47 分区解密**（`lumix_ml/decrypt_all.py`）
   - **Own the Signature（换公钥自签）**：RAM 替换 ECDSA P-256 验签信任锚 `K2@0x86F53722` + `K3@0x86F537C0` 并用本地私钥自签固件（`lumix_ml/keyswap_deploy.py`、`lumix_ml/build_selfsigned.py`），已在真机验证通过机身验签函数 `0x868C08C6`
   - **启动链钩取 & 任意载荷**：`lumix_ml/boot_exec.py`（`0x800003C4` detour → `0x8000E300`）、`lumix_ml/arb_exec.py`（`0x87086300`）
   - **SD 卡模块化基座工具（`sd_toolkit/`）**：零第三方依赖 GUI/CLI，生成与校验 `SD:\LUMIX_ML\PATCHES.BIN`（`LMLX` 协议 + CRC32 + 禁写区护栏），面向「一次最小化引导激活 + 后续永久免 USB、纯 SD 卡管理功能，拔卡即 100% 原厂」的架构形态
2. **易失性 RAM 视频规格与无限录制解锁模块**：
   - **19 半字纯 RAM 补丁**（0 刷写、支持电源键热重启持久化、拔电池即还原）：在原生 `Rec Quality (MOV)` 菜单解锁 **6K 3:2 Open Gate (`0x00ED`, `5952×3968` 23.98p)**、**5.9K 16:9 (`0x00F1`, `5888×3312` 23.98p)** 与 **全模式无限录制（`0x868261B6: 0x4628 → 0x2000`）**
   - 提供 **WebUSB 网页端**、**Android 离线 OTG 端**与 **macOS CLI**，且对应 19 半字补丁已内置为 `sd_toolkit/profiles_v29.json` 功能档案
3. **Windows 桌面端驱动、RAM 诊断与音效工具箱**：
   - **Windows 桌面应用**（Electron + React + Ant Design + Python 后端）：一键安装 `04DA:2370` WinUSB 驱动、只读 RAM 暂存区分布图诊断、28 项相机提示音/快门音效自定义替换（`0x8F000000` 暂存区）
   - 配套固件容器解析、明文重打包、`0x8631801A` 验签开关恢复脚本与 OSD/squashfs 分析脚本

> 详细的技术架构、信任链对照与持久化阶梯设计，请参阅 **[INTEGRATION_ARCHITECTURE.md](INTEGRATION_ARCHITECTURE.md)**。

---

## 仓库目录结构

| 目录 / 文件 | 说明 |
|---|---|
| [`DISCLAIMER.md`](DISCLAIMER.md) | **免责声明与法律风险提示（使用前必读）** |
| [`INTEGRATION_ARCHITECTURE.md`](INTEGRATION_ARCHITECTURE.md) | **技术架构总览**：换公钥自签、明文重打包、RAM 解锁与 SD 卡基座的分层设计与地址对照 |
| [`HANDOFF.md`](HANDOFF.md) | 项目交接文档（换公钥实证、打包顺序、QEMU `panasonic-pvc03v` 进展） |
| [`HANDOFF_LUMIX_S5_20261119.md`](HANDOFF_LUMIX_S5_20261119.md) | 早期研究交接归档 |
| [`ADDRESS_TABLE.md`](ADDRESS_TABLE.md) | DC-S5 V2.9 关键内存地址与范围速查表 |
| [`sd_toolkit/`](sd_toolkit/) | PC 端零依赖 SD 卡模块化基座工具（GUI/CLI、`LMLX` 协议、内置 V2.9 功能档案） |
| [`tests/`](tests/) | `sd_toolkit` 自动化离线单元测试（含对 V2.9 `program.bin` 原厂半字的自动校验） |
| [`lumix_ml/`](lumix_ml/) | 核心逆向与自签工具：`keyswap_deploy.py`、`build_selfsigned.py`、`ecdsa_recover.py`、`boot_exec.py`、`arb_exec.py`、`decrypt_all.py`、`ram_only_observer.py` 等 |
| [`integrations/s5-unlocker/`](integrations/s5-unlocker/) | 易失性 RAM 解锁客户端（WebUSB、Android OTG、macOS CLI 与可解锁模式参考） |
| [`integrations/lumix-tool/`](integrations/lumix-tool/) | Windows 桌面音效/内存诊断/驱动安装工具箱及固件研究脚本 |
| [`analysis/`](analysis/) | 静态分析结论、CFG、转储差分与验签分析记录 |
| [`firmware/`](firmware/) / [`dumps/`](dumps/) / [`keys/`](keys/) | 基线与研究窗口材料（Git LFS，**不含任何私钥**） |

---

## 快速开始

### 1. 零刷写即时解锁 6K Open Gate / 5.9K / 无限录制（RAM 级）
- **浏览器（Chrome WebUSB）**：打开 `integrations/s5-unlocker/docs/index.html`，相机按住 `PLAYBACK + AF/AE LOCK` 开机进入服务模式（`04DA:2370`），连接 USB-C 一键解锁。
- **Android 手机**：使用 `integrations/s5-unlocker/android/` 构建离线 APK，USB-C OTG 即插即解锁。
- **Windows 驱动配置**：可使用桌面工具内置的一键 WinUSB 驱动安装向导，或参阅 `integrations/lumix-tool/docs/DRIVER_SETUP.md`。

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

# 命令行：列出内置档案（含原生菜单 6K/5.9K + 全模式无限录制）
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

---

## 免责声明与法律风险提示

- **仅供个人学习与技术研究**：本仓库内容仅用于个人合法自有设备的固件结构分析与安全研究，禁止用于任何商业用途、非法破解或违反当地法律法规的行为。
- **与厂商无关**：本项目与 Panasonic Corporation（松下电器）无任何关联、授权或背书关系。
- **风险自担**：服务模式操作、内存改写及固件自签/刷写均不在官方支持范围内，可能导致设备故障、数据丢失、保修失效或永久性变砖。所有代码与文档均按“现状（AS-IS）”提供，不提供任何明示或暗示的担保，作者与维护者不对任何直接或间接损失承担责任。
- **安全边界**：RAM 级工具仅修改易失性内存，拔电池即可恢复原厂；`lumix_ml/keyswap_deploy.py deploy` 同样仅修改 RAM 中公钥。**仅当用户主动将自定义固件包写入 SD 卡并经相机菜单执行更新时才会改写 Flash**，任何涉及 Flash 的实验前请务必先完成官方恢复回滚演练。
- 完整条款请见 **[DISCLAIMER.md](DISCLAIMER.md)**。

---

## 致谢

感谢以下社区项目与研究者的开源贡献（相关模块与原协议文件已保留于 `integrations/` 目录）：

- **[USER-HFC/Lumix_Tool](https://github.com/USER-HFC/Lumix_Tool)**：桌面端工具箱、WinUSB 驱动安装、RAM 诊断、提示音替换与固件研究工具。
- **[rileydeacon/s5-unlocker](https://github.com/rileydeacon/s5-unlocker)**（MIT License）：6K Open Gate / 5.9K 原生菜单与全模式无限录制的易失性 RAM 解锁实现。

