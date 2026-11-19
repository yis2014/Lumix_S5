# Panasonic DC-S5 固件研究交接

更新时间：2026-11-19  
工作区：`E:/desktop/LUMIX`  
目标：记录可复现资产、已证实事实、已排除路线和下一轮的安全起点。

## 一句话结论

Service USB 已证明可以读取和逐半字写入主核 RAM，也已经证明冷函数 detour 能在真机执行。机身固件的解密、验签和真正刷写入口仍未拿到。Linux 从核只看到解密后加载到 RAM 的 rootfs，主核 RTOS 和早期引导代码掌握真实 Flash 访问。

## 当前状态

- 相机基线为官方 V2.9，曾用 RAM 版本结构临时改成 2.0 后成功刷入官方 V2.8，再恢复到 V2.9。
- `0x800003C4` Reset 交接探针曾命中，证明低地址启动链会跳到主核入口 `0x86280004`。
- 增强捕获记录过 `SP=0x13000`、`LR=0x3C4`、`CPSR=0x600001D3` 和 `r1=0x00C5187D`。该窗口呈现普通系统/协处理器代码特征，尚未证明是 postboot。
- 镜头更新头部校验函数 `0x868C5E48` 的 Thumb detour 已有真机计数器从 0 增加到 2 的实证。该点是目前最可靠的冷函数代码执行入口。
- 主核入口 `0x868F9A0C` 的后续探针存在多次写入备份记录。最近一次写入是否仍在机身 RAM 中，不能由备份文件单独判断。重新接入 Service USB 后必须先只读核验，再进行任何写操作。
- `0x87086A00` 曾被误当作代码洞。其基线是重复的 `CD CC CC 3D` 浮点常量，属于活动表区，禁止再次使用。

## 已证实能力

| 能力 | 证据 | 状态 |
|---|---|---|
| Service USB 读 RAM | `lumix_ml/usb_link.py`，opcode `0x5C`，每次 1 KiB | 已验证 |
| Service USB 写 RAM | opcode `0x9C`，16-bit halfword，逐次读回确认 | 已验证 |
| 主核代码执行 | `analysis/S5代码执行实证_20261119.md` | 已验证 |
| OSD 绘制 | `0x8DC00000` Plane A，stride 4096，宽 1024 | 已验证 |
| RAM 版本伪装刷官方包 | `0x863B0000` 与 `0x863181E2` 改为 2.0 后可接受高版本官方包 | 已验证 |
| 主核明文转储 | `0x86280000–0x88000000` | 已完成 |
| Linux rootfs 明文提取 | `rootfs1_dump.bin`、`rootfs2_dump.bin` | 已完成 |

## 关键地址与内存图

| 地址或范围 | 含义 | 备注 |
|---|---|---|
| `0x80000000` | 低地址启动向量与常驻启动代码 | 与低地址别名关系已验证 |
| `0x800003C4` | Reset 链主核交接指令 | literal 指向 `0x06280004` |
| `0x80120800` | DTB 副本 | `dtb_120800.bin` |
| `0x83100000` | rootfs1 加载地址 | 3 MiB SquashFS |
| `0x83400000` | rootfs2 加载地址 | 10 MiB SquashFS |
| `0x86280000` | 主核 program 加载地址 | 已有 30,932,992 字节明文转储 |
| `0x868C5E48` | 镜头文件头/版本校验冷函数 | 已实证 detour 触发 |
| `0x868F9A0C` | 主核入口分支 | 原始首字节 `82 00 00 EA` |
| `0x87086300` | 曾使用的 rodata 代码洞 | 会覆盖字符串，使用前需恢复并读回 |
| `0x87086A00` | 活动浮点表区 | 禁止写入 |
| `0x8F000100` 起 | 暂存/捕获缓冲区 | 需先确认当前内容 |
| `0x8DC00000`、`0x8DF00000` | OSD 双缓冲平面 | 属于显示链 |
| `0x90000000–0xA0000000` | 视频 DMA 和实时缓冲相关区域 | 禁止盲写 |
| `0x7F050000` | PL011 UART | DTB 标记 `console=ttyAMA,115200` |

## 固件与分区资产

- `S5___V29.bin`。保留为官方 V2.9 基线包，重复的 V2.8、测试包和镜头包位于 `full-archive-20261119` 标签。
- `firmware_table.json`。已解析 `program`、`postboot1..5`、`music`、`zimage`、`rootfs1/2` 的偏移和大小。
- `program_0x86280000.bin`。主核基线明文。
- `program_postboot_after_official_v29.bin`。官方 V2.9 升级后主核转储。
- `lowmem_0_2M.bin`。低地址启动代码及 Reset 链最小窗口。
- `lowmem_postboot_after_official_v29.bin`。官方升级后低地址内存转储。
- `rootfs1_dump.bin`、`rootfs2_dump.bin`。从 RAM 提取的解密后 SquashFS 镜像。
- `dtb_120800.bin`、`dtb_22ff000.bin`。设备树副本。
- `hidden_c5_focus.bin`。隐藏地址区的最小只读窗口，保留用于后续差分。
- `lowphys_0_64K.bin`、`a7_region.bin`、`keyregion.bin`、`keyregion_big.bin`。与启动、协处理器和密钥材料复核相关的必要窗口。

## 已确认的执行链

```text
0x80000000  Reset vector
    -> 0x80000050  关闭 IRQ/FIQ、MMU/cache，设置 SP=0x13000
    -> 0x80000134  清理与复制启动区
    -> 0x8000019C  进入片内表/寄存器初始化
    -> 0x800001E8  初始化事件结构
    -> 0x800003B8  cache/sync
    -> 0x800003C4  LDR PC，跳到 0x06280004
    -> 0x86280004  主核 program 入口
```

低地址启动代码没有出现可直接识别的 `UPD\0`、`FW_UPDATE_MODE`、NAND、AES 或 ECDSA 明文。postboot 更可能位于 BootROM/早期引导上下文，或在主核交接后短暂加载并释放。

## 机身更新链判断

- 主核 `program` 中的 UPD、AES-CTR、P-256 代码与镜头更新字符串绑定，不能据此代表机身更新。
- 机身更新日志位于 `Netmw_set_wlv_camctrl_request` 附近，字符串包括 `FW_UPDATE_MODE[IN] fw_ver=%s`。
- 官方包与改头包的行为对照表明，单改版本字段会在约 25% 阶段退出。目录副本、组件摘要、加密载荷和外层认证信息需要保持一致。
- 官方 V2.9 升级完成后，Service USB 常驻 RAM 没有保留 postboot 明文镜像，也没有出现可验证的机身密钥。
- Linux rootfs 使用 `mtd-ram`，只看到引导程序解密后放入 RAM 的镜像。rootfs 中没有可直接读写真实 Flash 的用户态工具。

## 已排除路线

- 主核四组 ECDSA/AES 钩子对机身更新没有触发。
- 镜头验签包装函数的恒真返回只影响镜头路径，不能放行机身包。
- 直接修改 music、版本头或少量目录字段，均未形成可刷包。
- 对主核、Linux、低地址和已扫高内存做静态密钥表搜索，没有得到可验证的机身密钥。
- 把 `0x87086A00`、`0x87086800` 一类活动表区当作代码洞会导致重启或掉线。
- 全零 BSS 区不适合作为持久代码洞，系统启动会清零。
- 拔电池会清除所有 RAM 探针、计数器和补丁。实验状态只适合电源键热重启。

## 可靠工具

- `lumix_ml/usb_link.py`。连接、读块、半字写入、备份和回滚。
- `lumix_ml/deploy_validator_detour.py`。镜头头部校验 detour 的编码、自测和部署。
- `lumix_ml/key_oracle.py`、`key_matrix.py`、`key_matrix2.py`。已知明文预言机和有限候选矩阵。
- `lumix_ml/build_dump_payload.py`。离线生成 RAM 复制型 payload。
- `lumix_ml/build_fwupdate_entry_probe.py`。机身更新入口探针生成器。
- `lumix_ml/read_fwupdate_entry_dump.py`、`read_nand_dump.py`、`read_dump.py`。捕获区和转储读取。
- `lumix_ml/dtb_parse.py`、`lowmem_scan.py`、`scan_highmem.py`。设备树、低地址和高内存只读分析。
- `lumix_ml/ram_only_observer.py`。只读采样启动入口、捕获区和活动表，不写 RAM、不执行载荷。

## 交接时第一步

1. 相机接入 Service USB 后只读读取 `0x868F9A0C`、`0x87086A00`、`0x87086300`、`0x8F000100`、`0x8F000200`、`0x800003C4`、`0x8000E400`。
2. 确认 `0x87086A00` 是否仍为原始浮点表。若不是，先依据对应 JSON 备份恢复，并读回验证。
3. 确认主核入口是否仍为 `82 00 00 EA`。只有确认目标、代码洞和缓冲区状态后，才允许新探针写入。
4. 继续沿 `0x87F2CCFA` 的 `tbb` 分发表解析机身更新 case，优先找只读捕获点。
5. 若需要硬件路线，优先观察 `0x7F050000` 对应的 UART bootlog。UART 只能用于观测和系统入口确认，不能直接假设能读真实 Flash。

## 下一阶段优先级

### A 级

获取早期引导或主核机身更新入口的只读捕获。目标是确认 postboot 装载地址、验签调用顺序和 Flash 读路径。

### B 级

在已证明可触发的冷函数上做小型内存复制 payload，把明确地址窗口复制到安全 RAM 缓冲区，再通过 `0x5C` 读回。每次只改一个目标，保留完整备份。

### C 级

定位 RAM 中已解密的 music 数据。先做内存版声音替换验证，验证播放链后再考虑持久化写入。

### D 级

确认 UART、BootROM 或恢复模式是否提供可观测的引导命令。公开资料没有证明特定 Stubby/SD 引导方案适用于 S5，需以真机日志为准。

## 公开仓库上传范围

`main` 是轻量交接版，保留继续分析所需的文档、脚本、地址表、必要转储、官方 V2.9 基线和密钥材料。完整原始包保存在 `full-archive-20261119` 标签。大文件使用 Git LFS，逐字节校验记录在 `MANIFEST_SHA256.txt`。工作区中的 `third_party`、`.workbuddy` 和与 S5 研究无关的目录没有纳入轻量版。

## 主要本地文档

- [`analysis/资产复盘与切入点_20261119.md`](analysis/资产复盘与切入点_20261119.md)
- [`analysis/低地址Reset加载跳转CFG_20261119.md`](analysis/低地址Reset加载跳转CFG_20261119.md)
- [`analysis/postboot_dump_diff_20261119.md`](analysis/postboot_dump_diff_20261119.md)
- [`analysis/S5代码执行实证_20261119.md`](analysis/S5代码执行实证_20261119.md)
- [`analysis/S5交接_20261119.md`](analysis/S5交接_20261119.md)
- [`analysis/S5攻关复盘_20261119.md`](analysis/S5攻关复盘_20261119.md)

## 交接口径

文档中的“已验证”只指本地文件、转储或真机读回有对应证据的事项。备份文件只说明某次写入前后的计划值，不能替代当前机身读回。任何新的硬件动作都从只读状态审计开始。
