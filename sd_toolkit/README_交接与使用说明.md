# LUMIX DC-S5 SD 卡模块化基座工具 — 交接与使用说明

> 版本：`v0.1.0`  
> 适用机型 / 固件：Panasonic LUMIX DC-S5（`pvc03v`），V2.9（`0x00000290`）  
> 运行环境：Windows 10/11 + Python 3.10+（**零第三方依赖**，仅用标准库 + 内置 `tkinter`）

---

## 一、工具定位与架构

本工具是 LUMIX S5 **“一次最小化引导激活 + 后续永久免 USB、纯 SD 卡加载功能”** 路线的 PC 端基座工具链。

```text
[PC 端基座工具 (本包)]
  ├── 桌面 GUI (app_gui.py) / 命令行 CLI (cli.py)
  ├── 生成、校验、解析 SD:\LUMIX_ML\PATCHES.BIN (LMLX 协议)
  └── 自动扫描可移动 SD 卡、原子写入、时间戳备份、一键恢复原厂

[机身侧 SD Loader (待真机阶段 2 联调)]
  └── 开机在 SD 卡挂载后读取 \LUMIX_ML\PATCHES.BIN，
      逐项校验 Magic + 固件版本 + CRC32 + 原厂半字一致后应用到 RAM；
      无文件或拔卡即 100% 原厂启动。
```

---

## 二、压缩包目录结构

```text
LUMIX_S5_SD基座工具_v0.1.0/
├── README_交接与使用说明.md      # 本文档
├── launch_sd_tool.bat           # 双击启动图形界面（GUI）
├── run_tests.bat                # 双击运行离线自测套件
├── sd_toolkit/
│   ├── __init__.py
│   ├── patch_format.py          # LMLX PATCHES.BIN 编解码、CRC32 与禁写区安全校验
│   ├── profiles.py              # 功能档案加载与合并校验
│   ├── profiles_v29.json        # V2.9 功能档案库（内置 6K Open Gate 示例）
│   ├── sd_manager.py            # Windows SD 卡扫描、原子部署、备份、回滚、官方恢复
│   ├── cli.py                   # 命令行入口
│   └── app_gui.py               # Tkinter 零依赖桌面应用
└── tests/
    ├── __init__.py
    └── test_sd_patch_tool.py    # 8 项自动化单元测试
```

---

## 三、快速上手

### 1. 图形界面（推荐）
直接双击根目录的 `launch_sd_tool.bat`（或终端执行 `python -m sd_toolkit.app_gui`）：
* **Tab 1 · SD 卡功能管理（日常免 USB）**：
  1. 插入 SD 卡后点击「刷新磁盘」（离线演练可点「选择目录...」指定任意本地文件夹）。
  2. 勾选需要启用的功能档案，右侧实时预览主核 VA、Service 别名与原值/新值。
  3. 点击「一键部署到 SD 卡」，自动写入 `SD:\LUMIX_ML\PATCHES.BIN` 与 `manifest.json`，旧文件自动备份至 `LUMIX_ML\backups\`。
  4. 点击「禁用/恢复原厂」会备份并删除 `PATCHES.BIN`，插回相机即恢复原厂。
* **Tab 2 · 基座激活与官方恢复**：只读检测 Service USB（`VID_04DA&PID_2370`）状态、查看安全激活清单、一键复制官方 `S5___V29.bin` 到 SD 卡根目录。
* **Tab 3 · PATCHES.BIN 校验与日志**：反解析任意 `PATCHES.BIN` 文件并验证 CRC32。

### 2. 命令行（CLI）
```powershell
python -m sd_toolkit.cli drives
python -m sd_toolkit.cli list-profiles
python -m sd_toolkit.cli verify-fw --program-bin analysis\decrypted_S5___V29\program.bin
python -m sd_toolkit.cli deploy H:\ --profile s5_v29_opengate_6k
python -m sd_toolkit.cli inspect H:\
python -m sd_toolkit.cli revert H:\
```

### 3. 运行自测
双击 `run_tests.bat` 或执行：
```powershell
python -m unittest discover -s tests -p "test_sd_patch_tool.py" -v
```
> 若工作区存在明文 `analysis\decrypted_S5___V29\program.bin`，测试会自动额外核验内置档案的原厂半字；独立解压运行（无 `program.bin`）时会自动跳过该项，其余测试全部执行。

---

## 四、`LMLX` `PATCHES.BIN` 二进制协议与安全边界

文件固定路径：`SD:\LUMIX_ML\PATCHES.BIN`（小端字节序）。

### Header（24 字节）
| 偏移 | 长度 | 字段 | 说明 |
|---|---|---|---|
| `0x00` | 4B | `magic` | 固定 ASCII `"LMLX"` (`0x584C4D4C`) |
| `0x04` | 2B | `format_ver` | 固定 `0x0001` |
| `0x06` | 2B | `flags` | bit0 = `1` 开启 `BOOT.LOG` 诊断日志 |
| `0x08` | 4B | `fw_version` | 目标固件版本（V2.90 = `0x00000290`） |
| `0x0C` | 4B | `entry_count` | 条目数 `N`（上限 `256`） |
| `0x10` | 4B | `payload_crc32` | 全部条目字节的 IEEE CRC32 |
| `0x14` | 4B | `reserved` | 必须为 `0` |

### Entry（每条 8 字节，共 `N` 条）
| 偏移 | 长度 | 字段 | 说明 |
|---|---|---|---|
| `+0x00` | 4B | `target_va` | 主核运行态 VA（如 `0x06E3DB1C`；输入 `0x86xxxxxx` 会自动归一化） |
| `+0x04` | 2B | `expected_orig` | 写入前必须匹配的原厂半字（防版本错配/写偏） |
| `+0x06` | 2B | `new_val` | 写入的新半字 |

### 内置安全护栏（`patch_format.py`）
* 强制 2 字节对齐；
* 限制安全写入窗口 `[0x06280010, 0x0BFFFFFE]`，拦截未映射黑洞区（`>= 0x0C000000`）；
* 硬编码拦截项目已确认禁写区：`0x06280000`（program 头）、`0x066C22B4`（memcpy）、`0x068F9A0C`（主核入口）、`0x07086400..0x070864FF` 与 `0x07086A00..0x07086AFF`（活动浮点表）；
* 自动检测多档案合并时的地址冲突。

---

## 五、离线逆向交接记录（供机身侧 SD Loader 联调使用）

以下地址均基于明文 `analysis/decrypted_S5___V29/program.bin`（主核 VA 基址 `0x06280000`，Service 别名 `0x86280000`）静态反汇编定位：

### 1. 主核 SD 卡文件系统公共 API（Thumb-2）
| 函数 | 主核 VA | 调用参数 | 备注 |
|---|---|---|---|
| `FS_GetDriveHandle` | `0x065d3e76` | `(drive_idx, &drive_handle)` | `0`=槽1(`A:`)，`1`=槽2(`B:`) |
| `FS_Open` | `0x065d36ae` | `(drive_handle, &fd, path, access=0, disp=2, extra=0)` | `path` 不带盘符前缀，返回 `0` 成功 |
| `FS_Read` | `0x065d376c` | `(fd, buf, size, &bytes_read, 0, 0)` | 返回 `0` 成功 |
| `FS_Write` | `0x065d380c` | `(fd, buf, size, &bytes_written, 0, 0)` | 可用于写 `BOOT.LOG` |
| `FS_Close` | `0x065d3722` | `(fd, 0)` | 常规关闭 |

### 2. SD 卡挂载完成阶段候选切入点（待真机只读观测确认）
* **首选候选**：`0x06470124` 之后（媒体挂载管理器调用 `0x065d3612` 成功并填充 `[r4+0x18..0x30]` 后，`[r4+0x04]` 直接持有 `drive_handle`，兼容双卡槽）。
* **备选候选**：`0x064d4472` 之后（卷信息读取 `0x065d3eac` 之后，同模块检查 `CACHE.DAT`）。

---

## 六、自定义功能档案 JSON 规范

可在 GUI 中通过「导入自定义 JSON...」加载外部功能包，格式如下：

```json
{
  "schema_version": 1,
  "fw_version": "0x00000290",
  "fw_label": "LUMIX DC-S5 V2.9",
  "profiles": [
    {
      "id": "my_custom_profile",
      "name": "自定义功能名称",
      "category": "分类",
      "risk": "低",
      "status": "测试中",
      "description": "功能说明",
      "entries": [
        { "addr": "0x06E3DB1C", "orig": "0x0002", "new": "0x0000", "note": "说明" }
      ]
    }
  ]
}
```

---

## 七、后续真机联调前置顺序（重要）

1. **先做官方回滚演练**：确认相机可正常刷回官方 `S5___V29.bin`。
2. **先在纯 RAM 中验证 SD Loader**：确认挂载时机、栈空间与空洞在真机运行态安全，再用本工具生成的 `PATCHES.BIN` 验证插卡生效/拔卡还原。
3. **最后再做唯一一次最小化持久化更新**：完成后日常功能管理彻底脱离 USB 服务模式。
