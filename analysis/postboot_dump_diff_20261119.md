# 官方 V2.9 升级后 postboot 转储与差分

## 采集

- `lowmem_postboot_after_official_v29.bin`：`0x80000000–0x84200000`，约 66 MiB
- `program_postboot_after_official_v29.bin`：`0x86280000–0x88000000`，约 29.5 MiB
- 采集时机：官方 V2.9 升级完成后重新进入 Service USB

## 结果

- 两个版本结构均恢复为 `90029002`，官方升级已完成并清除了 RAM 版本补丁。
- 主核程序相对 `program_0x86280000.bin` 仅有约 45 KiB 差异，差异集中在运行时数据区和少量重复的表区，未出现新的 postboot 明文镜像。
- 低地址区与旧基线的差异主要是 Linux 运行时数据。能够找到内核自带的 OpenSSL、ECDSA、P-256 和通用 AES 字符串，但这些落在 Linux 加密库范围内，没有出现 Panasonic 更新链的 `FW_UPDATE_MODE`、`UPD\0` 或 `Netmw` 明文。
- `0x80000000` 启动向量、`0x80120800` DTB、`0x83100000` rootfs1、`0x83400000` rootfs2 和 `0x86280000` program 的固定映射仍然有效。

## 当前判断

官方升级后的 Service USB 可读内存没有保留 postboot 明文或机身密钥。第二阶段代码可能在更早的引导上下文中短暂执行后被释放，也可能位于未覆盖的内存区。下一步需要针对启动后瞬时阶段做早期捕获，或从低地址启动代码继续静态追踪加载/跳转路径。
