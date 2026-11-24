# 从 SD 卡执行程序的可行性调查

> 目标：判断能否让 S5 运行外部 SD 卡上的程序（类似 S9 的 Magic Lumix 思路）。
> 结论：**原理上可行，但需要先有代码执行 + 找到文件 API 地址**；存在一条"改更新器"的捷径值得优先研究。

---

## 1. 关键发现：固件使用「消息 ID → 字符串」日志系统

反汇编中反复出现：

```asm
movw r1, #0xC040        ; 消息 ID
bl   0x868E59A0         ; 日志分发（参数 r1 = 消息 ID）
```

这解释了为什么所有 `AVIO_ReadLUTFile`、`CFS_Open(%s)` 这类字符串**在全盘都搜不到指针引用**
（字面量 / ADR / movw-movt 三种方式都试过）：它们不存在直接寻址，而是由日志系统按 ID 查表。

**影响**：不能用"字符串 → 引用 → 代码"的常规逆向路径，必须改成：
- 从日志调用点反推函数体
- 或先恢复消息表（ID → 字符串），再按 ID 反查调用点

## 2. 相机有完整的文件系统 API（postboot3）

| 函数 | 地址（字符串） | 说明 |
|---|---|---|
| `CFS_Open(%s)` | 0x877AAB64 | 打开文件 |
| `CFS_Read` | 0x877DA994 | 读 |
| `CFS_Write` | 0x879C0078 | 写 |
| `CFS_Seek` | 0x877DA874 | 定位 |
| `CFS_Close` | 0x877B3804 | 关闭 |
| `CFS_GetFileSize` | 0x877B3464 | 文件大小 |
| `CFS_GetFileInfo` | 0x877B3884 | 文件信息 |
| `CFS_Ioctl` / `CFS_IoctlEx` | 0x877AAB98 / 0x877AAC20 | 控制 |
| `CFS_SyncEx` | 0x877AAF98 | 同步 |

这些是**日志标签**，真实函数地址需按第 1 节的方法反推。

## 3. 一个现成的"按路径读文件"入口：`\restore.bin`

反汇编 0x87734606 处的命令处理函数：

```asm
87734606  push {r0-r3, r4-r6, lr}
87734608  cmp.w r0, #0x390        ; 命令 id = 0x390
8773460E  adr  r2, #0x58          ; r2 = "\restore.bin"（0x87734668）
87734612  beq  #loc_87734618
87734614  movs r0, #2             ; 未知命令 → 返回 2
87734618  ...
          bl   0x868E5948         ; 系统调用层（program 内）
          bl   0x868E5950
          bl   0x868E594C
```

要点：

- 命令 **0x390** = "restore"，从 `\restore.bin` 读取内容
- 文件操作通过 `0x868E5948 / 0x868E5950 / 0x868E594C` 这组 **program 内的系统调用桩**
  （postboot3 通过它们访问主核的底层服务）
- 路径是硬编码的，但说明**主核具备"从存储读文件"的能力**

## 4. 可行性链（逐环状态）

| 环节 | 是否具备 | 证据/缺口 |
|---|---|---|
| ① 设备上有代码执行 | ✅ | 参考项目已实证：`0x868C5E48` 打 Thumb detour，计数器 0→2 |
| ② RAM 可写、可跨热重启存活 | ✅ | 本会话实测（验签补丁、PCM 数据） |
| ③ 能从存储读文件 | ✅ 存在，地址待定位 | CFS API 字符串已确认；调用点可反推 |
| ④ 把文件读进 RAM | ✅ 同上 | CFS_Read 存在 |
| ⑤ 跳转到读入的代码 | 需实现 | 只需一条 `blx`/`bx`，payload 内即可 |
| ⑥ 让 payload 常驻（每次开机自动跑） | ❌ | RAM 补丁拔电池即失效 |

**结论**：①~⑤ 串起来就是"从 SD 执行程序"，技术上可行；⑥ 的持久化需要刷写，目前被启动链验签阻塞。

## 5. 值得优先研究的捷径：改「更新器」

主线更新器（postboot5 的 `0x87F4D32E`）本身就在做：

```
读 SD 上的固件文件 → 解析容器 → 校验 → 写入 flash
```

如果把它**改成"读到 RAM 就跳转执行"**，就得到了一条不写 flash 的 SD 执行路径，而且它已经内置了
文件读取和容器解析，省掉了 CFS 地址定位的工作。

风险：更新器是刷写流程的核心，改错可能让相机无法更新（但不影响正常启动）。

## 6. 已排除的分支

| 分支 | 结果 |
|---|---|
| Linux 侧热插拔/插卡脚本 | ❌ 无（rootfs 里没有 mdev/udev 执行规则） |
| Linux 侧 init 脚本扫描 SD | ❌ 无（`rcS` 只跑 `S02/S03/S10/S20`） |
| `netstart` 挂载 | 仅挂载 `/dev/mtdblock1`（rootfs2）到 `/mnt/rfs2`，与 SD 无关 |
| 菜单/配置触发 | ❌ 菜单无相关项 |

## 7. 候选函数：postboot3 的 `0x877AAAA0`

反汇编 `0x877AAAA0` 得到：

```asm
877aaaa0  push {r4,r5,r6,r7,lr}
877aaaa2  sub  sp, #0x4c
877aaaa4  mov  r6, r3
877aaaa6  mov  r7, r2
877aaaa8  mov  r4, r1
877aaaaa  movs r1, #0x38
877aaaac  mov  r5, r0
877aaaae  mov  r0, sp
877aaab0  blx  #0x8782bd38        ; memset 类
877aaab8  strd r0, r4, [sp, #0x38]
877aaabc  adds r0, r4, r7
877aaabe  strd r0, r4, [sp, #0x40]
877aaac4  bl   #0x877aa4f4        ; 取上下文
877aaac8  add  r2, sp, #0x38
877aaaca  movw r1, #0xc040        ; 日志消息 ID
877aaace  bl   #0x868e59a0        ; 日志分发
...
```

它紧邻 `CFS_Open(%s)` 等日志串，很可能是 **CFS_Open 的包装/实现之一**。
下一步可以反汇编它的调用者（BL 到 0x877AAAA0）来确认参数语义。

## 8. CFS 操作分发器（已完整解码）

`0x877AADE0` 处是一个 **TBB 跳转表分发器**，按操作码 `r6`（0..0xB）分发。
完整解码后，这些操作全部是**存储 IO / 流操作**，不是 open/read/close：

| 操作码 | 函数 | 语义（由 adr 引用的日志串确定） | 系统调用 |
|---|---|---|---|
| 0 | 0x877AAD80 | `CFS_SyncEx(CFS_SYNC_FSDATA, ...)` | 0x868E5970 |
| 1 | 0x877AAD1A | `CFS_GetWriteUnit` + `SyncEx` | 0x868E5958, 0x868E5970 |
| 2 | 0x877AACB2 | `CFS_SetFinalizeBuf` | 0x868E5958, 0x868E5970 |
| 3 | 0x877AAB12 | `CFS_GetFa` / `SetFa`（TRUE/FALSE） | — |
| 4 | 0x877AAAA0 | `CFS_Ioctl(SET_AVREADBUF)` | 0x868E59A0 |
| 5 | 0x877AAA72 | `CFS_Ioctl(SET_AVREADBUF)` | 0x868E59A0 |
| 6 | 0x877AAA48 | `CFS_Ioctl(SET_AVREADBUF)` | 0x868E59A0 |
| 7 | 0x877AA8C2 | `CFS_Ioctl(HDD_ACTIVE/BLOCK_WRITE)` | 0x868E59A0, 0x868E597C |
| 8 | 0x877AA83A | `CFS_Ioctl(IOC_HDD_TEMPERATURE)` | 0x868E59A0, 0x868E597C |
| 9–11 | inline | 返回码处理（`CFS_??? Ret`） | — |

> **更正上一轮的推测**：`0x877AAAA0` 不是 CFS_Open，而是 `Ioctl(SET_AVREADBUF)`。

### CFS_Open / CFS_Read 的字符串为何找不到引用

- `CFS_SyncEx`、`CFS_GetWriteUnit` 等字符串**有** `adr` 引用（可直接定位函数）
- `CFS_Open(%s)`、`CFS_Read`、`CFS_GetFileSize` **没有**字面量/ADR/movw-movt 引用
- 全 postboot3 CFS 代码区（0x877A8000–0x877DC000，212KB）扫描无命中

说明 open/read 这一类走的是**另一套日志机制**（消息 ID 查表），与前一类不同。
要拿到它们，仍需要恢复消息表，或改从调用方（媒体模块/更新器）反推。

## 10. 第 4 轮补充：导入表与路径拼接

- postboot1 的导入表位于 `0x87311B00` 起（每项 4 字节 `b.w` 跳转），共 100+ 项，
  目标分布在 program（0x866Cxxxx）与 postboot5（0x87Fxxxxx）
- 更新 worker 大量调用导入项 `0x87311CA0` → `0x866C18C8`，反汇编确认是 **strcpy**
  （worker 在拼文件路径，共 17 处）
- postboot5 内含固件更新相关字符串：
  - `FW_UPDATE_MODE[IN] fw_ver=%s`
  - `LENS_FW_UPDATE_MODE[IN] fw_ver=%s`
  - `NETMW_WLV_CAMINF_FW_DOWNLOAD_ADDRESS addr=%x size=%ld`

## 11. 最终结论

**能不能从 SD 卡执行程序？**

| 判断 | 说明 |
|---|---|
| 原理上 | ✅ **可以**。设备具备：代码执行（detour 已实证）、RAM 可写、文件系统 API、跳转指令 |
| 现成路径 | ❌ **没有**。无菜单入口、无 SD 热插拔脚本、无"从 SD 加载并执行"的既有功能 |
| 实现方式 | 必须自己写 payload：调用文件 API 读入 SD 文件 → 跳转执行 |
| 持久化 | ❌ 需要刷写，被启动链验签阻塞（RAM 补丁拔电池即失效） |

**结论一句话**：S5 具备执行外部程序的所有底层能力，但没有任何现成入口；
要做"SD 卡执行程序"必须自己构建 payload，且每次开机都要重新注入。

## 12. 进一步排除：三种寻址方式都没有引用

为定位文件 API，做了系统的引用搜索（工具：`js/find_pcrel_fast.js`、`js/find_movwt.js`）：

| 目标字符串 | PC 相对 (ADDW/SUBW) | 字面量指针 | MOVW/MOVT |
|---|---|---|---|
| `SYS_File_Open/Read/Seek/Close/GetSize` | 0 | 0 | 0 |
| `CFS_Open(%s)` | 0 | 0 | 0 |
| `A:\DCIM\G_DW.TXT` 等 SD 路径 | 0 | 0 | 0 |
| （对照）普通日志串 `0x87777550` | **2** ✅ | — | — |

同模块内普通日志串可正常引用，而上述目标三种方式全部为 0 ——
说明它们要么通过**基址寄存器 + 偏移**访问，要么是**未接线的代码路径**。
静态找 open/read 的收益已经很低。

## 13. 可执行程序空间

program 镜像内部有一块 **320 KiB 零区** `0x86360000..0x863B0000`，与代码同页映射，
**可执行性是构造保证的**。程序基址定为 `0x86370000`，可用 **256 KiB**。

> 暂存区 `0x8F000000` 虽然大，但可能是 XN（不可执行）页，不适合放代码。

## 14. 现行方案（不依赖相机文件 API）

```
程序文件放在 SD 卡  →  PC 读取该文件
                    →  服务模式写入相机 RAM 0x86370000
                    →  挂钩子 0x8647994C（ldr.w pc 尾跳，保留 lr）
                    →  半按快门 → 程序执行 → bx lr 返回
```

工具：

```bash
python tools/load_program.py push   X:\lumix_prog.bin
python tools/load_program.py verify X:\lumix_prog.bin
python tools/load_program.py restore
```

挂钩安全性已确认：调用方 `0x86478458` 不检查包装函数返回值，且栈平衡。

## 15. 待完成

1. **相机验证**（阻塞中）：注入 22 字节标记程序 → 半按快门 → 读 `0x8F300000`
2. 验证通过后：把真实程序（更大的 Thumb 代码）放到 `0x86370000`
3. 自动加载：需要找一个开机/周期运行的挂钩点（当前用半按快门触发）

## 16. 新线索：更新模块的 GOT 文件 API（postboot5）

在更新 worker（`0x87F4D32E`）同一模块里找到一套完整的文件 API 日志标签：

| 字符串 | 地址 | 引用点 |
|---|---|---|
| `GOT_Check_SDFreeSize` | 0x87F4C858 | 0x87F4C586 (`adr`) |
| `GOT_File_Open` | 0x87F4CCA8 | 0x87F4C914 (`adr`) |
| `GOT_File_Write` | 0x87F4CD98 | 0x87F4C9EE (`adr`) |
| `GOT_File_Close` | 0x87F4CD06 | 待查 |
| `GOT_LOAD_END` / `GOT_LOAD_CANCEL` | 0x87F4CE3F / 0x87F4CE5F | 待查 |

**意义**：这是第一次找到**有实际代码引用**的文件 API（`adr` 命中，不是消息表）。
如果 `GOT_File_Open` 能按路径打开 SD 文件，方案 B 就能落地。

**待办**：
1. ~~从 0x87F4C914 向前找函数入口~~ → **已找到：`0x87F4C602`**
2. 确定 `GOT_File_Open` 的参数（路径指针？上下文结构？）与返回值（句柄/状态码）
3. 写测试 payload 调用它打开 `A:\test.txt`，用标记确认

### GOT_File_Open 调用链（已还原）

```
0x87F4C602  push.w {r3-r8,sb,sl,fp,lr}
            r5 = r1 (arg2), r4 = r0 (arg1)
            b   0x87F4C8CC            ; 中间是字符串数据
0x87F4C8CC  adr r0, =0x87F4CCA8       ; "GOT_File_Open" 日志标签
            ldr r0, [pc,#0x3cc]       ; 全局上下文
            movw fp, #0x5E2
            ldr.w sl, [pc,#0x3c4]
            cbz r0  -> r4 = 1 (错误码)
            cbz r5  -> r4 = 2
            ... 参数校验 ...
0x87F4C904  blx 0x8782BD3C            ; memset/memcpy 类
0x87F4C908  ldr r5, [pc,#0x398]
0x87F4C914  adr r0, =0x87F4CCA8       ; 日志
            ...
            bl  0x87311650  -> b.w 0x867749BA   ; program 模块
            bl  0x87311658  -> b.w 0x867749D0   ; program 模块
```

两个导入的真实目标：

- `0x867749BA`：`movs r0,#1; bl 0x867411F8; ... b.w 0x86740EAC`
- `0x867749D0`：`push {r1,r2,r3,r4,r5,lr}`，检查 r0/r2 非空，
  以 `(r1=3, r2=1, r3=0)` 调 `0x86470A96`

**下一步**：给 `0x87F4C602` 构造参数（疑似 r0=会话/上下文，r1=路径或模式），
在 payload 里调用并观察返回值/标记。

## 16.5 新突破：SD 驱动 API（绕开文件系统直接读扇区）

program 模块内含完整的 SD 卡驱动，日志串全部可定位：

| 函数 | 字符串地址 | 引用点 | 函数入口 |
|---|---|---|---|
| `SDD_Init` | 0x863C0044 | — | — |
| `SDD_Open` | 0x863C06F4 | 0x863C0316 | **0x863C0312** |
| `SDD_Read` | 0x863C0758 | 0x863C0512 | **0x863C0504** |
| `SDD_Write` | 0x863C0DA8 | 0x863C09CC | — |
| `SDD_Ioctl` | 0x863C007C | 0x863BFE22 | — |

`SDD_Read` 的寄存器形态（从反汇编读出）：

```asm
863c0504  push.w {r0-r8,sb,sl,fp,ip,lr}
          r6 = r0        ; 句柄/上下文指针
          sl = r1        ; 指向扇区号的指针（代码会 ldr r1,[sl]）
          r7 = r2        ; 目的缓冲区
          sb = r3        ; 扇区数量
          ... 校验 r0/r1 非空 [r6] 非空，[r6+4] 与 2 比较 ...
```

**意义**：如果不调用相机文件系统，可以自己用 `SDD_Read` 读原始扇区、自己解析 FAT——
这条路不依赖那些找不到引用的 `CFS_Open`/`SYS_File_*`。

**前提**：需要合法的 SD 驱动句柄（由 `SDD_Open`/`SDD_Init` 建立），以及正确的 DMA/中断上下文。

## 16.6 SDD_Read 的真实参数（日志格式串揭示）

```c
SDD_Read> pb_Buff=%lX, uw_Count=%ld, uw_Offset=%ld
```

即：**缓冲指针、数量、偏移** —— 这是一个可以直接读扇区的接口。

寄存器映射（从 0x863C0504 反汇编读出）：

```
r0 = 上下文    → 0x08AB07A4（[0]=0x08AF57C8 卡信息，[+4]=1，符合内部检查）
r1 = 偏移相关   （代码里 ldr r1,[sl]，可能是指向偏移量的指针）
r2 = pb_Buff   （目的缓冲）
r3 = uw_Count  （数量）
```

**上下文已验证**：`0x88AB0774 + 0x30 = 0x88AB07A4`，其 `[0]` 非空、`[+4] ≤ 2`，
正好满足 `SDD_Read` 开头的检查条件；且全局 `+0x28` 状态为 1（SD 已打开）。

## 16.7 SDD_Ioctl 命令表（已导出）

`SDD_Ioctl` 入口 **0x863BFE16**，内部用命令表分发（0..0x34），表在虚拟地址
`0x06A17AD4`（物理 `0x86A17AD4`）。

已对应出的命令（通过每个处理函数里的 ADR 日志串匹配）：

| 命令 | 处理函数 | 功能 |
|---|---|---|
| 0x05 | 0x863C2D36 | SetEventCbf |
| **0x08** | 0x863C22F0 | **GetSectorSize / GetStatus（只读）** |
| **0x09** | 0x863C1E2C | **GetCardCapacity / GetCardInfo / GetStatus（只读）** |
| 0x0A | 0x863C1DF2 | GetCardCapacity / GetCardInfo |
| 0x0B | 0x863C1C1E | Erase（危险） |
| 0x0D | 0x863C1BB8 | CheckWp / Erase |
| 0x0F | 0x863C2328 | GetStatus |
| 0x11 | 0x863C2276 | GetSectorSize / GetStatus |
| 0x22 | 0x863C1F40 | GetExtCSD |

调用形态（从开卡包装与分发器读出）：`SDD_Ioctl(ctx, cmd, arg1, arg2)`，
ctx = `0x08AB07A4`。

**建议**：先用命令 0x08（GetSectorSize）做安全探测——只读、不改卡状态。
成功后再尝试 `SDD_Read`。

## 17. 工具链注意事项

`js/find_pcrel_fast.js` / `js/find_adr_fast.js` / `js/find_movwt.js` 是纯编码扫描器，
绕过反汇编器的对齐问题。已发现并修复的问题：

- JS 位运算把 0x87xxxxxx 截断为负数（改用算术对齐）
- capstone-js 对部分 16 位指令解码错误（`b40c` push 被解码成 `lsrs`）
- 线性反汇编遇到 TBB 跳转表/字符串区会错位

## 18. 原结论（保留）

**结论一句话**：S5 具备执行外部程序的所有底层能力，但没有任何现成入口；
要做"SD 卡执行程序"必须自己构建 payload，且每次开机都要重新注入。
