# DC-S5 破解项目 · 最新交接（2026-11-22）

## 一句话状态

固件代码已明文掌握，免密钥改机链路已打通到"固件文件已构建并通过校验"，
**只剩最后一步：把探针固件刷进相机验证**。刷写必须由人操作 SD 卡 + 相机菜单。

## 1. 目标完成度

| 目标 | 状态 | 证据 |
|---|---|---|
| 解出明文代码 | ✅ | loader3/zboot/postboot1-5 哈希吻合；program 明文在 RAM；rootfs1/2 已提取 |
| 不刷机 DIY | ✅ | OSD 覆盖层实测可见；RAM 版本/验签开关写入验证；参考项目已实证 detour 代码执行 |
| 出一版固件 | 🟡 | 三个固件已构建并校验（0 mismatch），等待刷写验证 |

## 2. 关键地址

| 地址 | 含义 |
|---|---|
| 0x8631801A | **更新验签开关**：0=验签，1=跳过 |
| 0x863B0000 / 0x863181E2 | 机身版本字段（各 2×u16，当前 0x0290=2.90） |
| 0x86280000 | program 加载地址（16MB，RAM 中是解压后代码） |
| 0x87267000.. | postboot1-5（LOAD 格式，哈希验证通过） |
| 0x83100000 / 0x83400000 | rootfs1 / rootfs2（squashfs） |
| 0x8DC00000 / 0x8DF00000 | OSD 双缓冲平面（行 stride 4096） |
| 0x86F10040 | 按键事件码表（KEY_Q_MENU=0x4000） |
| 0x87F4D32E | 固件更新 worker（postboot5 内） |
| 0x0C11DA38 / 0x0C2110A4 | 更新流程全局结构 G / S（S+0x334=模式） |

## 3. 容器格式要点（免密钥路径的基础）

- 记录 0x5C 字节：name[12] @+0，img @+0xC，size @+0x10，flash @+0x14，
  **flags @+0x18**，sha256 @+0x1C，iv @+0x3C
- flags=2 明文、flags=3 密文
- 外层 CRC32 @0x40 覆盖 file[0x200:]
- 版本门 @0x1C（两个 u16），须高于机身版本

**易错点（本轮踩过）**：flags 是 +0x18，不是 +0x14（+0x14 是 flash 地址）。
改成 flags=2 时必须同时写入明文 blob，否则会把密文当明文刷进去。

## 4. 固件文件（out/）

| 文件 | 改动 | 校验 |
|---|---|---|
| FW_probe_postboot2.bin | postboot2 flags 3→2，明文与官方一致 | ✅ |
| FW_probe_program_ramcopy.bin | program 明文（RAM 副本，内容未改） | ✅ |
| FW_candidate_v299.bin | program 明文 + 版本 2.90→2.99 | ✅ |

SD 卡（G:）当前已写入 **FW_probe_postboot2.bin**（CRC 有效）。

## 5. 下一步操作（需要人）

1. 拔卡 → 插回相机
2. 热重启（电源键，**不要拔电池**，否则 0x8631801A 会清掉）
3. 开机 10 秒内：MENU → 设置 → 固件版本 → 更新
4. 回报结果

判读：
- 开始刷写并重启 = 链路成功
- 提示"已安装/无法更新" = 版本门问题（确认 RAM 版本 2.90、开关 1）
- 提示校验失败 = 开关未生效（相机安全）

## 6. 降级/恢复

服务模式 → 0x863B0000/0x863B0002/0x863181E2/0x863181E4 写 0x0200（2.00）
→ 0x8631801A 写 1 → 热重启 → 刷官方 S5___V29.bin。

前提：相机还能进服务模式。启动链未被修改，这是本方案的风险边界。

## 7. 未完成/待研究

- 影像引擎固件（hm_/hr_/ipu_/nr_/rc_）不在可读 RAM；需 AES 密钥或 NAND 读取 payload
- music 分区明文未获取（声音改动的持久化受限）
- OSD 可见区域会被 UI 持续重绘，静态覆盖留不住；持久覆盖需挂钩重绘或 vblank 回调
- Q 键分发函数未定位（已有关键表、UIQMenu 符号线索）
- USB 直刷入口未找到（service 接口无 flash 命令；更新 worker 需被调用）

## 8. 工具

| 工具 | 用途 |
|---|---|
| tools/s5svc.py | 服务 USB 读写（0x5C 读、0x9C 写、0x9B 读字） |
| tools/lumixupd.py | 容器解析/校验/提取 |
| tools/repack.py | 免密钥重打包 |
| tools/build_fw.py | 构建候选固件 |
| tools/osdsnap.py | OSD 截图 |
| tools/osddraw2.py | RGB565 绘制（双缓冲半区） |
| tools/schedscan.py | 扫 AES key schedule |
| js/sqextract.cjs | squashfs 提取（含 fragment 修复） |
| js/disasm_linear.js | 顺序反汇编（Thumb-2） |

## 9. 档案

`archive/`：62 个文件。核心文档：
- `DERIVED/FLASH_PROCEDURE.md` 刷写/回滚流程
- `DERIVED/PLAINTEXT_COVERAGE.md` 明文覆盖清单
- `DERIVED/KEY_EVENT_TABLE.md` 按键码表
- `DERIVED/UPDATE_FLOW_NOTES.md` 更新流程结构
- `DERIVED/OSD_LAYOUT_NOTES.md` OSD 布局结论
- `ANALYSIS/FACTS.md` 已验证事实（F1-F21+）

## 10. 新增：一键恢复工具（2026-11-22）

`tools/recover.py` 读取/设置恢复所需状态：

    python tools/recover.py            # 只读查看当前状态
    python tools/recover.py --apply    # 版本字段写 2.00、验签开关写 1

刷写出问题且相机仍能进服务模式时，跑 `--apply` → 热重启 → 刷官方包即可回退。
当前实测状态：版本 2.90、验签开关 1（适合刷 2.91 的自定义固件）。
