# Panasonic S5 QEMU research prototype

这是一个**研究型** QEMU ARM machine，不是原厂 Panasonic S5 固件启动器。
实现目标是把公开 PVC02V Linux 设备树中可复核的板级地址，映射为一个可
观察的 Cortex-A7 参考模型，并用完全合成的 ARM payload 验证 RAM、UART、
SP804 和 SDHCI stub。

## 当前状态

| 项目 | 状态 |
| --- | --- |
| Windows 官方 QEMU | `11.1.0` 已安装并可运行 |
| stock machine | `virt` 等可用；不等于 S5 |
| 源码版本 | `third_party/qemu`，v11.1.0 |
| custom `-M s5` 源码 | 已加入工作树，并生成可重放 patch |
| custom QEMU 二进制 | 尚未生成；MSYS2/MinGW 已安装依赖，但 configure 仍失败，`NOT RUN/BLOCKED` |
| 合成 payload | 已生成，分类为 `SYNTHETIC-PAYLOAD` |
| 原厂 S5 V28/V29 启动 | 明确拒绝，`ENCRYPTED_OR_ENCODED_UNVERIFIED` |
| 私钥 | 未恢复；不能由公开 P-256 公钥/签名推导 |

## 参考地址（MODEL / PUBLIC-REFERENCE）

这些地址来自公开 PVC02V 参考 DTS，不应被表述为已经完整核实的 S5
MC801 硬件契约：

- RAM: `0x90200000`, `0x02f00000`（47 MiB）
- GIC distributor: `0x70001000`
- GIC CPU interface: `0x70002000`
- SP804 timer10: `0x7f02a000`, 参考 IRQ 24/25；QEMU 通用 SP804 暴露合并 IRQ 24
- UART2 / PL011: `0x7f052000`, 参考 IRQ 264
- SDIO2: `0x7c320000`，使用研究 stub，不是假装为 Panasonic SD 控制器

公开 DTS 的 `cpu@3` / `reg=<3>` 只作为 CPU affinity 参考。当前 machine
限制为一个 Cortex-A7；不据此声称 S5 已确认是某种 SMP 配置。

## 构建

### 已安装的 stock QEMU

```bat
scripts\install_qemu.cmd
```

也可以直接使用：

```text
C:\Program Files\qemu\qemu-system-arm.exe --version
```

### 自定义 QEMU

QEMU 官方 Windows 构建路径需要 MSYS2 的 MINGW64 环境。本机已存在
`C:\tools\msys64`，并已安装 gcc、Meson、Ninja、GLib、Pixman、DTC、zstd
等依赖；当前 configure 尝试仍遇到 `Unknown target name '0'`，所以不能把
源码实现伪装成已编译结果。需要在 MSYS2 MINGW64 shell 中重试并保留日志。

安装依赖后，在 Windows 命令提示符运行：

```bat
scripts\build_s5_qemu.cmd
```

或在 MSYS2 MINGW64 shell 中运行：

```bash
./scripts/build_s5_qemu.sh
```

脚本只编译 `arm-softmmu`，并在构建后检查 `-machine help` 是否包含 `s5`。
源码 patch 位于：

```text
patches/qemu/0001-arm-panasonic-s5-machine.patch
```

## 合成 smoke test

构建 custom QEMU 后：

```bat
scripts\run_s5_smoke.cmd
```

它会生成 `analysis/s5_qemu_20261101/s5_test_payload.bin`，再使用 QEMU
通用 loader 显式加载到 `0x90200000` 并设置 CPU0 PC。payload 会：

1. 向参考 UART 输出 `[S5 SYNTHETIC] PASS`；
2. 向 SDHCI stub 写寄存器并读取合成 `STUB` ID；
3. 在 RAM `+0x100/+0x104` 写入哨兵；
4. 写入**仅供测试的** exit MMIO 并请求 QEMU 退出。

这只能证明 `SYNTHETIC-PASS` / `MODEL`，不能证明原厂代码、原厂 parser、
加密包、相机功能或 `S5-BOOT-PASS`。

## 验证

```text
python s5_qemu/s5_test_payload.py \
  --output analysis/s5_qemu_20261101/s5_test_payload.bin \
  --manifest analysis/s5_qemu_20261101/s5_test_payload.json
python tests/test_s5_qemu.py
```

如果 custom QEMU 尚未编译，端到端 machine 检查会跳过并明确报告原因；其余
静态门禁仍会检查地址图、payload 摘要以及固件输入门禁。

## 固件和密钥边界

`S5___V28.bin` 与 `S5___V29.bin` 的关键 `loader/program/dtb/zimage/rootfs`
输入没有可验证的明文启动格式和入口。目录中的 target 值不是已证明的
运行时 VA/入口，不能直接喂给 CPU。更新目录的 P-256 签名只能验证目录
元数据；它不包含 AES 密钥，公开公钥和签名不能反推出 Panasonic 的 ECDSA
私钥。此仓库不实现密钥提取、猜测解密或第三方签名滥用。

因此结果标签严格区分：

- `STATIC`：文件和门禁审计；
- `MODEL`：公开参考地址/设备骨架；
- `SYNTHETIC-PASS`：合成 payload 在 custom machine 上通过；
- `REAL-CODE-PASS`：尚未达到；
- `S5-BOOT-PASS`：尚未达到且不能由本项目当前输入声称。
