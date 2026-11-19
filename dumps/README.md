# 必要转储

本目录保留用于启动链、主核、postboot 差分、rootfs、DTB、协处理器和密钥材料复核的最小窗口。

- `program_*` 是主核明文基线与官方 V2.9 升级后对照。
- `lowmem_*` 是 Reset 链和升级后低地址对照。
- `rootfs*_dump.bin` 是 RAM 中提取的解密后 rootfs。
- `dtb_*.bin` 是设备树副本。
- `hidden_c5_focus.bin`、`lowphys_0_64K.bin`、`a7_region.bin`、`keyregion*.bin` 是必要的定点窗口。

更大的高内存、阶段性 RAM 和重复转储位于 `full-archive-20261119` 标签。
