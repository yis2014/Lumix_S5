# SD 卡加载执行 —— 完整验证手册

> 所有代码已就绪。以下四步全部通过，即达成目标：
> **相机自己从 SD 卡读出程序并执行。**

## 准备

1. 相机连 USB，**按住 PLAY + AF-ON 开机**（服务模式）
2. SD 卡根目录放好 `LUMIX.BIN`（用下面的命令从 PC 复制）

```powershell
# 构建全部 payload
# （ARM GCC 在 tools/armgcc；若 pwsh 不可用，用同样参数手工调 gcc/objcopy）
payloads\build.ps1

# 把演示程序复制到 SD 卡（假设卡是 G: 盘）
python tools/prepare_sd.py G:\
```

## 第 1 步：验证 C 编译的代码能执行（零风险）

```bash
python tools/load_program.py push payloads/test_marker.bin
# 半按快门
python tools/payload_test.py check   # 或读 0x8F300010
```

期望：`0x8F300010 = 0xCAFEBABE`

## 第 2 步：验证 SD 上下文（零风险）

```bash
python tools/load_program.py push payloads/ioctl_probe.bin
# 半按快门
# 读 0x8F300080
```

期望：

```
+0  0xC1C1C1C1
+4  （返回值，通常 0）
+8  0x00000200   ← 扇区大小，关键
+12 0xC2C2C2C2
```

看到 `0x200` 说明上下文与调用约定正确。

## 第 3 步：读扇区 0（中等风险）

```bash
python tools/load_program.py push payloads/sd_probe.bin
# 半按快门
# 读 0x8F300020
```

期望：`+0=A1A1A1A1`、`+12=A2A2A2A2`，`+8` 是扇区 0 的前 4 字节。

## 第 4 步：从 SD 读程序并执行（目标达成）

```bash
python tools/load_program.py push payloads/fat_load.bin
# 半按快门
# 读 0x8F300040（loader 状态）和 0x8F3000A0（演示程序写入）
```

期望：

```
0x8F300040+0 = 0xB2B2     引导扇区解析完成
0x8F300040+1 = 0xB0B0     文件已加载并跳转
0x8F3000A0   = 0x5A5A5A5A  ← 演示程序执行了
0x8F3000A4   = 0x1234ABCD
```

**看到 `0x5A5A5A5A` 就证明：程序是从 SD 卡读出来并执行的。**

## 错误码

| 值 | 含义 |
|---|---|
| 0xE001 | 读扇区 0 失败（SDD_Read 调用问题） |
| 0xE002 | 找不到 FAT32 分区 |
| 0xE003 | BPB 解析失败 |
| 0xE004 | 根目录没有 LUMIX.BIN（检查文件名/复制） |
| 0xE005 | 文件为空或 > 60 KiB |
| 0xE006 | 读簇失败 |

## 出问题怎么办

- **死机**：拔电池（不要只按电源键）
- **E001**：`SDD_Read` 参数不对，回到第 2 步确认上下文，再调 `sd_probe`
- **E004**：确认 `prepare_sd.py` 复制成功、卡是 FAT32
- **`0xB0B0` 但没有 `0x5A5A5A5A`**：文件加载了但跳转/执行有问题，
  检查 `0x86360000` 处的内存内容是否等于 `LUMIX.BIN`

## 复原

```bash
python tools/load_program.py restore     # 恢复对焦音挂钩
python tools/trace_hook.py restore 0x8647994C f0b591b00d460446
```

拔电池即可彻底恢复原厂。
