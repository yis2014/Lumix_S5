# S5 固件中的 LUT 代码分析（AVIO 层）

> 结论先行：**S5 固件里有 LUT 文件读取与查表代码，但位于 AVIO 视频输出/监看层；
> 菜单未开放，媒体/编码模块也没有 LUT 阶段。**
> 所以「REAL TIME LUT 录制」不能靠改一个开关实现；监看端加 LUT 是可能的研究方向。

---

## 1. 证据：LUT 相关字符串（全部位于 program 段）

| 地址 | 字符串 |
|---|---|
| 0x86730FB8 | `CDL&LUT`（DestructiveItem 枚举：`OFF / CDL / LUT / CDL&LUT / Undefined`） |
| 0x867BE3AC | `AVIO_ReadLUTFile(id:%d addr:%x size:%ld)` |
| 0x867BE3E4 | `lut_data_size_str:%15s lut_data_size:%d read_count:%d` |
| 0x867BE428 | `LUT File Read Error (%d)` |
| 0x867BE444 | `r:%d g:%d b:%d tabel_num:%d index:%d` |
| 0x867BE5C0 | `AVIO_ViewAssistSet(output:%d type:%d id:%d)` |
| 0x867BE5F4 | `AVIO_PLANE_SetPinPInverse(%d -> %d)` |
| 0x867BE61C | `avio_get_lut(output:%d id:%d)` |

## 2. 反汇编位置

| 文件 | 范围 | 说明 |
|---|---|---|
| `docs/disasm/avio_lut_867be1f0.txt` | 0x867BE1F0–0x867BE6A0 | LUT 读取/解析主循环 |
| `docs/disasm/avio_lut_867be2c0.txt` | 0x867BE2C0–0x867BE3B0 | 解析循环尾部与日志调用 |

## 3. 解析器骨架（观察到的行为）

```
0x867BE1F0  ldr.w fp, [pc, #0x1e4]        ; 取上下文/错误码指针
0x867BE200  bl 0x867BDF48                 ; 取下一段（r0=缓冲指针, r1=剩余长度, r2=模式）
0x867BE208  movs r1,#0xa / strh [fp,#0xa] ; 写错误码 0xA（长度不足）
0x867BE222  bl 0x867BDF48                 ; 继续取段
0x867BE24A  bl 0x867BDF48
0x867BE264  bl 0x86837B04                 ; 日志输出
0x867BE278  cmp r3,#0x11 / cmp r3,#9      ; 校验字段 id（0x11、9 合法）
0x867BE290  adr r1,#0x150                 ; 指向格式串
0x867BE336  bl 0x86837B04                 ; 日志输出
```

要点：

- 辅助函数 **0x867BDF48**：按 `(ptr, remaining, mode)` 读取下一个数据段，返回解析到的长度；
  返回负值表示失败，随后写错误码（0xA、0xB、0xC、0xD、0xE、0x14、0x15 等）。
- 日志函数 **0x86837B04**：可变参数格式化输出。
- 字段 id 只接受 **9（0x9）** 与 **17（0x11）**，其余视为格式错误。
- LUT 表填写日志为 `r:%d g:%d b:%d tabel_num:%d index:%d`，即逐项写入 RGB 三元组，
  带 `tabel_num`（表号）与 `index`（索引）。

## 4. 对外接口（由日志串推断）

```c
int  AVIO_ReadLUTFile(int id, void *addr, long size);   // 读取并解析 LUT 文件
void *avio_get_lut(int output, int id);                 // 按 output/id 取 LUT
int  AVIO_ViewAssistSet(int output, int type, int id);  // View Assist（监看）
```

`output` 是输出通道（屏幕 / HDMI 等），说明 LUT 绑定在**输出端**而非编码端。

## 5. 当前阻塞点

1. **没有直接引用**：全盘搜索字面量、`ADR`、`movw/movt` 均未命中这些字符串的地址，
   说明它们很可能通过消息表（id → 字符串）引用，调用者尚未定位。
2. **菜单未开放**：`MC801_allmenu.xml` 中 0 处 LUT/CDL/ViewAssist。
3. **编码链路无 LUT**：媒体模块 postboot3 中无 LUT 引擎（唯一的 "CDL" 属于
   `VLC CDL(getmpf):ERR` 日志，与色彩无关）。

## 6. 可行性判断

| 目标 | 可行性 | 说明 |
|---|---|---|
| 菜单里出现 LUT 选项 | 低 | UI 资源里没有对应项，需要改 osddata/菜单结构（且需刷写） |
| 监看端套自定义 LUT | 中 | 需要调用 `AVIO_ReadLUTFile` + `avio_get_lut`，属于代码注入级研究 |
| 录制文件带 LUT | 很低 | 编码管线没有 LUT 阶段，需重写图像管线（且刷写被启动链验签阻塞） |

## 7. 建议的下一步

1. 定位 `AVIO_ReadLUTFile` 的调用者：从 AVIO 命令分发表（按命令 id 分发）反查，
   而不是继续搜字符串地址
2. 找到 LUT 数据的存放地址与表结构（`tabel_num` / `index` 的维度），确认是 17³ 还是 33³
3. 若找到可用的调用入口，先做**只读验证**：构造调用参数、观察 LUT 表是否被填充
4. 若监看端 LUT 可跑通，再评估能否把它接到 HDMI 输出（对录机有效）
