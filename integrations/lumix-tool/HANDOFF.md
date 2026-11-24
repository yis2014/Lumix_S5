# HANDOFF — 交给下一个分析者

这个工作区是松下 DC-S5 固件研究的一次完整会话产物（2026-11-19/20）。
所有结论、原始数据、工具都已整理进 `archive/`。

## 先看哪里

1. `archive/README.md` — 总览与目录说明
2. `archive/ANALYSIS/FACTS.md` — **已验证**的事实（每条都附证据与复现方法）
3. `archive/ANALYSIS/HYPOTHESES.md` — **未验证**的推断（附可信度与证伪方法）
4. `archive/ANALYSIS/OPEN_QUESTIONS.md` — 按价值排序的下一步
5. `archive/OBSERVATIONS/device-and-protocol.md` — 设备上看到的一切（USB、
   协议逐字节回复、菜单行为、时序）

## 数据分层（重要）

| 目录 | 性质 | 说明 |
|---|---|---|
| `RAW/` | 原始字节 | 从相机/官方下载得到后**未做任何修改**：固件、RAM dump 分块、探针 |
| `OBSERVATIONS/` | 观察记录 | 操作/AI 转写的设备行为与协议回复（含十六进制原文） |
| `DERIVED/` | 派生数据 | 由 RAW 计算或切出：合并 RAM、loader3 明文、反汇编、squashfs 镜像、分区表 |
| `ANALYSIS/` | 分析 | 事实、假设、问题、时间线（`zh/` 下是中文原始笔记） |
| `TOOLS/` | 工具 | 服务接口客户端、密钥扫描器、容器解析/重打包、capstone 反汇编脚本 |

`archive/MANIFEST.txt` 记录每个文件的大小与 SHA-256。

## 一句话现状

已能：进工厂模式（PLAY+AF-ON）、读 RAM（250 KB/s）、读明文固件段
（loader3/zboot 已用哈希验证）、反汇编 ARM32。

**最新突破**：运行时 DTB（`0x822FF000`）里的内核命令行是：

```
root=/dev/mtdblock0 slram=slram0,0x83100000,+0x00300000,slram1,0x83400000,+0x00A00000 console=ttyAMA,115200
```

也就是说 **rootfs 是通过 slram 挂在 RAM 里的**：`0x83100000`（3MB，rootfs1）
和 `0x83400000`（10MB，rootfs2）。当前 dump 只到 `0x83000000`，**差 1MB**。

## 最高价值的下一步

1. **接 UART（现在最短的路）**：`/etc/shadow` 里 `root::` 是**空密码**，
   `/etc/inittab` 在 `ttyAMA` 上跑 `getty`，内核命令行 `console=ttyAMA,115200`。
   找到主板上的串口测试点接 USB-TTL，直接就是 root shell——能跑 hello world。
2. **Venus 侧 `program` 分区**：相机 UI、SD 卡、固件更新都不在 Linux 侧，
   而在加密的 `program`（16MB，flags=3）里。S9 那种“从卡启动”若存在，
   只可能在这里——需要 AES 密钥才能读。
3. AES 密钥：已扫过 5 个 AES 表 ±128KB（30 万候选）无命中，可继续扩扫。

## 已经拿到的

- rootfs1（`0x83100000`，2.5MB）和 rootfs2（`0x83400000`，9.4MB）两张 squashfs
  已完整提取（**零错误**，171 + 384 个文件），打包在
  `archive/DERIVED/rootfs1_extracted.zip`、`rootfs2_extracted.zip`。
- **Linux 侧没有 SD 自动执行钩子**：`rcS` 只跑 `S02-mount/S03-modules/S10-ifup/S20urandom`。
- root 空密码 + 串口 getty → 物理串口即 root shell。

## 法律与安全

相机为用户本人所有；固件来自松下公开下载页。所有 USB 操作均为只读，
写操作码 `0x9C` 从未被工具构造。唯一一次设备修改是官方更新容器中
把一个**零长度**分区的目标地址改掉（详见 FACTS F7）。
