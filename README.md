# Lumix S5 lightweight handoff

这是 DC-S5 研究的轻量交接版。`full-archive-20261119` 标签保留上一版完整原始包，`main` 只保留继续分析所需的最小集合。

## 入口

- `HANDOFF_LUMIX_S5_20261119.md` 研究交接总览
- `ADDRESS_TABLE.md` 关键地址、范围和用途
- `analysis/` 当前结论、CFG、转储差分和验签记录
- `lumix_ml/` Service USB、探针、转储和静态分析脚本
- `lumix_ml/ram_only_observer.py` 默认只读的 RAM-only 状态捕获器
- `firmware/S5___V29.bin` 官方 V2.9 基线
- `dumps/` 主核、启动链、rootfs、DTB 和必要窗口
- `keys/` 镜头材料、公开验签公钥和 keyregion 窗口
- `MANIFEST_SHA256.txt` 全部文件校验

大文件使用 Git LFS。完整原始包仍可从 `full-archive-20261119` 标签获取。
