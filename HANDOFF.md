# 松下 LUMIX S5 固件逆向项目 — 交接文档

> 最后更新：2026-11-21
> 工作目录：`E:\desktop\LUMIX`
> 目标：获得固件签名能力（"own the signature"），最终在相机菜单加 "Hack By Zdm" 菜单项。

---

## 一、项目终极目标与当前所处阶段

| 目标 | 状态 |
|---|---|
| 获得固件签名能力（own the signature） | ✅ 已验证可行（RAM 级） |
| 持久化换公钥（冷启动永久生效） | ⏳ 待做（方向 A） |
| 加 "Hack By Zdm" 菜单项 | ⏳ 待做（方向 B） |
| S5 完整 QEMU 模拟环境 | ✅ 阶段2达成（从核 boot 到 rootfs 挂载+驱动加载；console 待重编内核） |
| 安全回滚演练（确认相机健康） | ⏳ 待做（方向 C，推荐先做） |

**核心路线**：不刷 ROM 的 Magic Lantern 思路（RAM 启动链钩取）+ 换公钥（own the signature）双线并行，最终目标是永久拿到签名能力后自由改固件。

---

## 二、已完成的里程碑（按时间线）

### 里程碑 1：固件解密 ✅
- AES 密钥 `194364775255595d04e48de2b15e5c2c`（5 轮 AES-128-CBC，IV=目录 aux16）。
- V2.8 / V2.9 全部 47 分区解密成功，产物在 `analysis/decrypted_S5___V28/`、`analysis/decrypted_S5___V29/`。
- 工具：`analysis/decrypt_all.py`。

### 里程碑 2：Magic Lantern 启动链钩取验证成功 ✅
- 工具 `lumix_ml/boot_exec.py`：0x800003C4 detour → cave 0x8000E300，复位早期执行任意 ARM 载荷。
- 支持 `--read/--write/--code`，热重启生效、拔电池还原（零持久化风险）。
- 含 `selftest/preflight/deploy/status/rollback` 子命令。
- 主核任意载荷执行：`arb_exec.py`（CAVE 0x87086300，跨热重启存活）。

### 里程碑 3：换公钥方案验证成功 ✅（本项目最重要突破）
- 目标：把机身 ECDSA 验签公钥换成我们自己的 → 自签任意固件通过机身验签。
- **时间线铁证**（顺序不可颠倒）：
  1. RAM 替换 K2@0x86F53722 + K3@0x86F537C0 的 64 字节公钥 → 我们的。
  2. 未断电、未冷启动（RAM 状态保持）。
  3. SD 卡放自签包 → 刷入 → **进度条走完、成功**。
- **逻辑自洽**：自签包用原厂 K2 验签=False；刷入时机身 RAM 公钥=我们的；成功 ⇒ 机身验签确实走 K2，换公钥真实生效。
- **推翻旧结论**：验签函数 0x868C08C6 不是"仅镜头验签"，实为机身固件更新验签。

### 里程碑 4：S5 QEMU machine 编译成功 + 内核完整启动到 rootfs ✅✅
- 从零编译出带自定义 `panasonic-pvc03v` machine 的 `qemu-system-arm.exe`。
- S5 的 Linux 内核（zImage，3.18.18）已能在 machine 上启动，**slram 注册成功 + squashfs 识别 + 网络栈初始化**，但**rootfs 挂载失败**（`mtdblock0 (driver?)` → `Kernel panic - VFS: Unable to mount root fs on unknown-block(31,0)`）。根因是内核缺 `CONFIG_MTD_BLOCK`（只编了 mtd_blkdevs 框架，没编 mtdblock.c 块驱动），slram 只出字符设备 /dev/mtd0 出不了 /dev/mtdblock0。**注**：早期记录"挂载成功"是误判，已纠正。
- 已建模（覆盖内核访问的全部地址，`guest_errors` 0 条）：GICv2（含松下 `cpu-offset=0x8000` per-cpu 布局，revision=2）、时钟/复位控制器 stub、slram RAM 盘、PL011 UART、SP804 timer、**ICC mailbox（0x80121000/0x80122000）+ doorbell（0x00060200）stub**。
- 启动命令（rootfs 需 `-device loader` 加载到 slram）：见 `qemu/s5/` 下 README/脚本。
- **唯一剩余硬阻塞 = console 无输出**，根因已彻底确证（非 QEMU 模型问题，且比初判更根本）：从 zImage 解压出 vmlinux.bin 静态搜索证实 **内核根本没编译任何物理串口驱动**（`pl011`/`PL011`/`ttyAMA`/`uart_register`/`serial8250`/`8250` 全部 NOT FOUND；而 `arm,sp804` 存在，故 sp804 能用作 clocksource）。amba 总线/OF platform 框架在、会枚举 `arm,primecell` 设备，但 driver 链表里无 pl011 匹配 → `console=ttyAMA` 落到 `colour dummy device`，所有 printk 只进 log_buf。`-d guest_errors` 运行 8 秒确认 guest 从未访问 0x7f050000（UART0）且零 unknown MMIO。次要因素才是缺 `of_clk_init`/`__clk_of_table`/`clkdev_init`。要修需重编内核开 CONFIG_SERIAL_AMBA_PL011，超出 QEMU 范围；当前 pmemsave+log_buf 读日志方案已满足观察启动需求。

---

## 三、关键地址模型（钉死，勿改）

### 固件打包结构（换公钥核心）
| 字段 | 偏移 | 说明 |
|---|---|---|
| 版本字段 | 0x1c / 0x2bc | 版本伪装（如 0x02a0 = 2.160） |
| digest | SHA256(fw[0x2A0:0x142C]) | 覆盖含版本字段 |
| 签名区 | 0x220:0x260 | r/s 小端 |
| CRC32 | 0x40 | crc32(fw[0x200:]) |

**正确打包顺序（踩坑修正，顺序错即失败）**：
```
① 改版本字段 0x1c/0x2bc
② 重算 digest = SHA256(fw[0x2A0:0x142C])
③ 自签（r/s 小端写 0x220:0x260）
④ 重算 CRC32 = crc32(fw[0x200:]) 写 0x40
```
约束：版本 0x2bc 在 digest 覆盖内、签名在 CRC 覆盖内。

### 验签/密钥库
| 项 | 地址 | 说明 |
|---|---|---|
| 验签函数 | 0x868C08C6 | 原厂字节 70b5b0b0，机身固件更新验签 |
| caller B | 0x868c708a | 读 K2 公钥 |
| K2 公钥数据 | 0x86F53722 | 64 字节，全字节反序 |
| K3 公钥数据 | 0x86F537C0 | 64 字节 |
| K2 证书项指针 | 0x06f53722 @0x86f537bc | |
| K3 证书项指针 | 0x06f537c0 @0x86f53858 | |
| 密钥库指针 | 0x06F53764 | 升级上下文+0x64，0x868C72DE 写入 |
| program VA base | 0x86280000 | 明文偏移 + base = VA |
| program 明文 K2 公钥偏移 | 0xcd3722 | 持久化改这里 |

**密钥库导航链**：密钥库指针 → 证书项 → 公钥指针 → 公钥数据本体。

### 内存/SoC 架构
| 项 | 值 |
|---|---|
| SoC | 松下自研 pvc03v（Cortex-A7 架构） |
| 主核 | 异构多核，前 3 核跑 RTOS（program.bin） |
| Linux 从核 | 第 4 核（cpu@3），单核 Cortex-A7 |
| DRAM 物理 | 0x80000000–0xC0000000 (1GiB) |
| Linux 从核内存 | 0x80200000 起，47MB（0x2f00000） |
| GIC | GICv2，`cpu-offset=0x8000`，cpu@3 → GICD@0x70019000 / GICC@0x7001A000 |
| UART | PL011@0x7f050000（console ttyAMA0） |
| zImage 加载地址 | 0x80200000 |
| 机身版本存储 | 0x863B0000 / 0x863181E2（当前 2.90） |
| 0x8C000000 起 | 未映射黑洞（读报 err=121） |

---

## 四、关键文件清单

### 换公钥工具
| 文件 | 用途 |
|---|---|
| `lumix_ml/keyswap_deploy.py` | 换公钥（selftest/status/deploy/rollback/selfsign） |
| `lumix_ml/build_selfsigned.py` | 一键正确打包（改版本→digest→自签→CRC） |
| `analysis/our_keypair.json` | 我们的 P-256 密钥对（priv=64c82c5e...） |
| `keyswap_backup.json` | 原厂公钥备份（可 rollback） |
| `S5___V29_selfsigned_2a0.bin` | 最终自签包（版本伪装 2.160） |

### Magic Lantern 工具
| 文件 | 用途 |
|---|---|
| `lumix_ml/boot_exec.py` | 启动链钩取（0x800003C4 detour） |
| `lumix_ml/arb_exec.py` | 主核任意载荷执行 |

### QEMU
| 路径 | 说明 |
|---|---|
| `qemu/qemu-11.1.1-src/` | QEMU 11.1.1 源码（已改 meson.build 兼容 Windows） |
| `qemu/qemu-11.1.1-src/hw/arm/panasonic-pvc03v.c` | 自定义 machine 源码 |
| `qemu/qemu-11.1.1-src/build/qemu-system-arm.exe` | 编译产物（含 pvc03v machine） |
| `qemu/qemu-11.1.1-src/pregen.py` | 预生成 sh 脚本输出（绕过 MSYS2 sh 崩溃） |
| `qemu/qemu-11.1.1-src/patch_ninja.py` | patch build.ninja 把 sh 调用改 no-op |
| `qemu/s5/HARDWARE.md` | S5 硬件画像 |
| `qemu/PLAN.md` | QEMU 阶段规划 |
| `qemu/reference/z9-qemu|z8-qemu` | WonderLantern 参考源码 |

### 日志
| 文件 | 说明 |
|---|---|
| `.workbuddy/memory/2026-11-21.md` | 完整项目日志（含所有里程碑细节） |

---

## 五、QEMU 编译环境（重要，接手必读）

编译 QEMU 有多个**环境层面的坑**，已全部踩通，切勿重新踩：

1. **必须用 MSYS2 原生 bash**（`/c/tools/msys64/usr/bin/bash.exe -lc '...'`），不能用 Git Bash（MSYS 路径转换会把 `E:/` 弄成 `E:/e/`）。
2. **环境变量**：`PATH=/mingw64/bin:/usr/bin:$PATH` + `TMPDIR/TMP/TEMP` 指向工作区内 `qemu/tmp`。
3. **改过的 meson.build 两处**（Windows 兼容，不要还原）：
   - 跳过 `chmod a+x run`
   - 跳过 `symlink-install-tree.py` postconf
4. **MSYS2 sh.exe 崩溃**：meson 调 sh.exe 时 `NtCreateDirectoryObject` 失败 → 已用 `pregen.py` 预生成 6 个 shell 脚本输出 + `patch_ninja.py` 把 6 条 sh COMMAND 改 no-op。
5. **config-poison.h 需过滤** `TARGET_NOT_USING_LEGACY_LDST_PHYS_API` / `_NATIVE_ENDIAN_API` 两宏。
6. **machine 必须用 `DEFINE_MACHINE_ARM` 宏**（`hw/arm/machines-qom.h`），不能用 `type_init`（会被静态链接优化丢弃）。

编译命令（在 qemu-11.1.1-src 目录）：
```bash
/c/tools/msys64/usr/bin/bash.exe -lc '
cd /e/desktop/LUMIX/qemu/qemu-11.1.1-src && \
export PATH="/mingw64/bin:/usr/bin:$PATH" && \
export TMPDIR="E:/desktop/LUMIX/qemu/tmp" TMP="E:/desktop/LUMIX/qemu/tmp" TEMP="E:/desktop/LUMIX/qemu/tmp" && \
cd build && ninja -j8 qemu-system-arm.exe'
```

启动命令：
```bash
qemu-system-arm.exe -M panasonic-pvc03v -cpu cortex-a7 -m 47M \
  -kernel zimage.bin -dtb dtb.bin -nographic -serial mon:stdio
```

---

## 六、待决策的三个方向

| 方向 | 内容 | 风险 | AI 建议 |
|---|---|---|---|
| **A 持久化换公钥** | 改 program 明文 K2 公钥(0xcd3722) + AES 重加密 + 重算 + 自签 + 刷入 | 中（写 flash） | 等回滚演练通过后再做 |
| **B 回归菜单目标** | 加 "Hack By Zdm" 菜单项 | 中 | 依赖持久化完成 |
| **C 安全回滚演练** | 确认能刷回官方 V2.9，验证相机健康 | 低 | **推荐先做** |

---

## 七、QEMU 状态与下一步

**阶段 2（Linux 从核 boot 到 rootfs 挂载 + 驱动加载）已达成**。用 `-device loader` 加载 rootfs1/2.bin 到 slram（0x83100000/0x83400000）后，`pmemsave` 导出内存读 log_buf 可验证完整启动日志：内核 3.18.18 完整启动 → `VFS: Mounted root (squashfs) on 31:0` → 加载 cpu_iccdrv/icsm 驱动 → 稳定停在 ICC 等主核（从核预期终点）。`guest_errors` 0 条，machine 模型已完整覆盖内核访问的所有地址。

剩余方向（按优先级）：

1. **console 输出**（唯一硬阻塞，非 QEMU 模型问题）— 根因（已修正定论）：内核**没编译任何物理串口驱动**（pl011/8250 全无，vmlinux 静态搜索确证），`console=ttyAMA` 落 dummy。次要因素是缺 `of_clk_init`/`__clk_of_table`。**要修需重编内核开 CONFIG_SERIAL_AMBA_PL011**，超出 QEMU 范围；pmemsave+log_buf 方案已够用。
2. **主核 ICC 握手模拟** — 从核 ICC 驱动（0x8012xxxx mailbox）在等主核 program.bin 响应；若要推进到用户态 init，需模拟主核的 ICC 回包（或 patch 从核跳过等待），属层 B 范畴。
3. **阶段 3（主核 program.bin 加载调试）** — 尚未开始，见 PLAN.md 层 B。

方法论参考 WonderLantern（灰盒）：合成外部输入 + 显式功能模型 + 硬件断点服务，**绝不 patch guest 指令/寄存器**。未知 MMIO 访问会被 `unknown MMIO` trap 打印出来，逐个补模型即可。

---

## 八、重要边界与注意事项

1. **换公钥当前是 RAM 级（非持久）**：冷启动后公钥还原原厂，自签包再刷会失败。
2. **0x8C000000 起是未映射黑洞**：读取会报 err=121 设备挂起，扫描时务必避开，否则 USB 句柄泄漏（需重新插拔恢复）。
3. **squashfs(LZO) 重打包**：拍摄参数菜单在 Linux 核 rootfs（LZO 压缩），直接字节替换会破坏压缩流，需自写 LZO 解包→改→重打包（已被"不刷 ROM"决策排除）。
4. **osdover 字符串池**：系统设置菜单在主核 osdover 分区（UTF-16LE），但 Service 模式下主核 UI 未加载，字符串池不在 RAM。
5. **残留进程**：python PID 20784 是 Doubao 沙箱环境进程，非我方脚本，勿动。
6. **个人文件安全**：所有操作均在 `E:\desktop\LUMIX` 工作区，未涉及个人目录清理。

---

## 九、一句话总结

**换公钥（own the signature）路线已在真机上验证可行（RAM 级），QEMU 自定义 machine 已编译成功并让 Linux 内核跑起来。下一步建议：先做安全回滚演练（方向 C）确认相机健康，再推进持久化换公钥（方向 A）和菜单目标（方向 B）；QEMU 侧继续迭代补外设模型推动内核打印 console 输出。**
