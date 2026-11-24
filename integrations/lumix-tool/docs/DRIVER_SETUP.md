# 驱动安装指南（服务模式 USB / WinUSB）

> 适用：Windows 10/11，Panasonic DC-S5 服务模式（`04DA:2370`）
> 目的：让上位机（Electron 应用 / `tools/s5svc.py`）能通过 USB 读写相机 RAM。

---

## 0. 为什么需要装驱动

相机有两种 USB 身份：

| 模式 | VID:PID | 类 | Windows 默认行为 |
|---|---|---|---|
| 正常模式（PTP） | `04DA:2382` | PTP/MTP | 系统自动装 MTP 驱动，可传照片 |
| **服务模式** | `04DA:2370` | 厂商自定义 `ff/a0/b0` | **没有自带驱动**，需要手动绑定 WinUSB |

服务接口使用 Bulk IN `0x82` / Bulk OUT `0x01` 传输自定义帧，系统默认不会加载可用驱动。
因此需要用 **LumixTool 内置安装**或 **Zadig** 把该接口绑定到 **WinUSB**（微软通用 USB 驱动）。

> 这是一次性操作：绑定后，只要接口 PID 仍是 `2370`，驱动就一直有效。

---

## 1. 准备工作

1. 一根**数据线**（不是纯充电线）
2. 相机电池电量充足
3. 使用 LumixTool 内置安装；若需手动回退方案，可自行下载 [Zadig](https://zadig.akeo.ie/)（单文件，免安装）
4. 关闭其它可能占用相机的软件（图片导入工具、PTP 客户端等）

---

## 2. 让相机进入服务模式

1. 相机**关机**
2. 按住 **`PLAY`**（回放键）+ **`AF-ON`** 不放
3. 保持按住，**开机**
4. 松开按键，用 USB 线连接电脑

进入成功后，设备管理器里会出现 `04DA:2370`（可能显示为未知设备/复合设备）。

> 退出服务模式：关机再开机即可（普通开机就是正常模式）。
> 如果按 `PLAY + AF-ON` 开机后设备仍是 `2382`，说明没进服务模式，重试。

---

## 3. 一键安装（LumixTool 内置）

适用 Windows 10/11。打开应用「连接指南 → 安装驱动」，先按第 2 节进入服务模式并连接 USB，再点击「一键安装驱动」，在 Windows UAC 弹窗中授权。驱动操作不依赖 Python；相机连通性验证仍需要 Python 3。

应用只调用 Windows 内置 PowerShell、证书工具和 `pnputil`，不下载、不捆绑第三方可执行文件。具体过程：

1. 将随应用分发的 INF 和安装脚本复制到临时目录（兼容打包后的 `app.asar`），以管理员权限启动脚本。
2. 在 `LocalMachine\My` 创建或复用有效的 `CN=LumixTool Driver Signing` 自签名代码签名证书，导出公钥证书，并加入本机 `Root`（受信任的根证书颁发机构）和 `TrustedPublisher`（受信任的发布者）。私钥标为不可导出，不随应用分发。
3. 使用 `New-FileCatalog -CatalogVersion 2` 生成目录文件，使用此证书和 SHA256 签名，再运行 `pnputil /add-driver <inf> /install`。临时文件在结束后清理，证书和已加入驱动存储的包保留。
4. 使用 Windows 自带的 WinUSB，不提供 `.sys` 或 co-installer。INF 的提供者为 `LumixTool`，仅匹配 `USB\VID_04DA&PID_2370` 和 `USB\VID_04DA&PID_2370&MI_00`（接口 0），包含 amd64、arm64、x86 模型，不匹配普通模式 `2382`。它注册的 `DeviceInterfaceGUIDs`（REG_MULTI_SZ）必须为 `{CDE53111-593A-43C9-AB10-EA9DACF2C573}`。

**证书影响：**上述证书在整台电脑的信任存储中生效，并非仅对当前账户或这两个硬件 ID 生效；硬件绑定范围由 INF 限制。管理员可使用本机保存的私钥签名，因此应只安装可信来源的 LumixTool。卸载应用本身不会自动删除证书或驱动，请使用下述回滚功能。

**安装结果的含义：**成功表示 `pnputil` 接受了驱动包，不保证它已替换当前绑定。Windows 的驱动排名、签名策略（包括 Secure Boot / 企业策略）可能拒绝该本机签名目录或保留已有驱动；通用 `New-FileCatalog` 生成的目录也需要在目标 Windows 上验证其驱动包兼容性。本实现尚需真实 Windows + 相机验证，不能将本机代码签名等同于微软硬件认证。应用不会修改启动配置或签名策略。若失败，可展开结果查看步骤、退出码及完整输出，结合 `C:\Windows\INF\setupapi.dev.log` 排查，并使用下节 Zadig 手动方案。

状态检测无需管理员权限，优先用 `Get-PnpDevice -PresentOnly` 和设备属性输出 JSON，再读取 USB 枚举键下 `Device Parameters\DeviceInterfaceGUIDs`。它区分：

| 状态 | 下一步 |
|---|---|
| 未检测到服务模式设备 | 进入服务模式，检查 USB 数据线与端口 |
| 检测到普通模式 2382，请进入服务模式 | 按 `PLAY + AF-ON` 开机后重新检测 |
| 已连接但未安装驱动（或驱动错误 / GUID 缺失） | 点击「一键安装驱动」 |
| 已绑定 WinUSB，接口 GUID 尚无法确认 | 重新检测，必要时用设备管理器验证；不标为正常 |
| 驱动正常 | 已确认 WinUSB、无设备问题和所需 GUID；步骤 1 完成并前进 |

连接指南打开时每 5 秒检测一次，也可以点击「重新检测」。若 PowerShell 查询不可用，回退到 `pnputil /enum-devices /connected /ids`，只使用稳定的设备 ID / 服务名，不依赖中英文标签。此回退无法确认 GUID，不会仅凭显示名称就宣称驱动正常。检测失败与设备未连接分开显示。驱动正常后，仍需在第 3 步验证相机通信。

现有 `app/python/s5svc.py` 从非 `MI_00` 的 USB 枚举根键构造设备路径，保持未修改。虽然 INF 和状态检测覆盖复合设备接口 0，只有该接口绑定成功并不保证这个现有后端能打开它；必须在实际复合枚举机身上完成第 4 节验证。如果 GUID 已正确注册但后端仍失败，应保留枚举路径与日志进一步排查。

### 内置回滚与证书清理

在步骤 1 展开「高级 → 卸载驱动」。可勾选「同时移除 LumixTool 本机签名证书」，然后授权 UAC：

- 只删除 `pnputil /enum-drivers` 中**原始名称为 `lumixtool_winusb.inf` 且提供者为 `LumixTool`** 的已发布 `oemNN.inf`，执行 `/delete-driver oemNN.inf /uninstall /force`。不删除其它厂商驱动。
- 可选清理 `Root`、`TrustedPublisher` 和 `My` 中上述主体、颁发者都匹配的本机自签名证书（含 My 中的私钥）；默认保留证书。删除驱动失败时不会继续清理证书。
- 未安装时重复卸载、已安装时重复安装均可；取消 UAC 会显示取消结果并允许重试。重复安装可能仍受 Windows 驱动排名影响。
- 完成后重新插拔 USB；普通开机的 `04DA:2382` 使用系统 MTP。必要时按 Windows 提示重启；这不会使服务模式 `2370` 自动变为普通模式。

管理员也可手动运行脚本（`ResultPath` 必须为可写的绝对路径；每次返回包含 `ok / step / message / pnputilExit / output` 的 JSON）：

```powershell
# 在管理员 Windows PowerShell 中，工作目录为 app
powershell -NoProfile -ExecutionPolicy Bypass -File .\driver\install-driver.ps1 -ResultPath "$env:TEMP\lumixtool-install.json"
powershell -NoProfile -ExecutionPolicy Bypass -File .\driver\uninstall-driver.ps1 -ResultPath "$env:TEMP\lumixtool-uninstall.json" -RemoveCertificate
```

### 用 Zadig 手动绑定 WinUSB

1. 运行 `zadig.exe`
2. 菜单 **Options → List All Devices**（必须勾选，否则看不到相机）
3. 在设备下拉列表里选择 **`04DA:2370`**（或名称里带 `2370` 的那一项）
   - 相机可能有多个接口，选**接口 0**（Interface 0）通常是服务接口
4. 右侧目标驱动选择 **WinUSB**（`WinUSB (v6.1.7600.16385)` 或类似）
5. 点击 **Install Driver**（或 **Replace Driver**），等待完成
6. 完成后设备管理器里该设备的驱动提供者应显示 **WinUSB**

### 验证绑定成功

- 设备管理器 → 找到该设备 → 属性 → 驱动程序 → 提供程序：`WinUSB`
- 设备管理器 → 属性 → 详细信息 → `设备接口 GUID`，应能看到：
  `{CDE53111-593A-43C9-AB10-EA9DACF2C573}`
  （本项目的客户端就是按这个 GUID 枚举接口的）

---

## 4. 用工具验证连通性

相机保持服务模式、USB 连接，运行：

```bash
cd app
python python/s5focus.py status
```

预期输出类似：

```json
{"connected": true, "id1_addr": "0x06AA3180", "id1_size": 14464, "custom": false, "body_version": "0x0290"}
```

或者用更底层的自检：

```bash
python tools/s5svc.py selftest
```

能读到数据即说明驱动 + 协议都正常。

---

## 5. 回退 / 卸载驱动

想让相机恢复成普通 MTP 设备：

1. 设备管理器 → 找到 `04DA:2370` 设备
2. 右键 → **卸载设备**，勾选「删除此设备的驱动程序软件」
3. 拔掉 USB，重新插上
4. Windows 会重新识别（正常模式下为 `04DA:2382`，自动装 MTP 驱动）

使用内置驱动包时，优先使用第 3 节「高级 → 卸载驱动」清理驱动存储；需要移除证书时一并勾选清理。普通模式由 `2382` 身份和系统 MTP 驱动决定，无需把服务接口替换成 CDC 等其它驱动。

---

## 6. 常见问题（本项目实际遇到过的）

| 现象 | 原因 | 处理 |
|---|---|---|
| `python s5focus.py status` 输出 `{"connected": false}` | 设备没枚举到，或没进服务模式 | 确认 PID 是 `2370`；重新按 `PLAY+AF-ON` 开机 |
| 报错 `CreateFile failed - is WinUSB bound to 04DA:2370? (GetLastError=2)` | 接口没绑定 WinUSB，或 GUID 不对 | 用 Zadig 重新绑定；确认设备接口 GUID 是 `{CDE53111-593A-43C9-AB10-EA9DACF2C573}` |
| `WinUsb_Initialize failed (GetLastError=6)` | 句柄未以重叠（overlapped）方式打开 | 本项目客户端已用 `FILE_FLAG_OVERLAPPED`，无需处理；自己写客户端时必须加 |
| Zadig 列表里看不到相机 | 没开 `List All Devices`，或相机不在服务模式 | 勾选 Options → List All Devices；重新进服务模式 |
| 绑定后程序仍连不上 | 其它程序占用了设备 | 关闭相机伴侣、图片导入、PTP 工具后重试 |
| 传输中途相机无响应 | 发送了 `0x70` 等会冻结机身的命令 | **永远不要发 `0x70`**；重新插拔 USB 恢复 |

---

## 7. 自动化/进阶说明

- 客户端（`tools/s5svc.py`）通过 SetupAPI 枚举设备，读取注册表
  `Device Parameters\DeviceInterfaceGUIDs` 得到接口 GUID，再用 `CreateFile` +
  `WinUsb_Initialize` 打开。
- 设备打开标志必须包含 `FILE_FLAG_OVERLAPPED`，否则 `WinUsb_Initialize` 返回
  `ERROR_INVALID_HANDLE (6)`。
- 每次 1 KiB 读（`0x5C`）约 4 ms；半字写（`0x9C`）约 2 ms，可用 `settle` 参数调节。
- 服务模式会在一段时间空闲后自动关机，长时间操作时注意。

---

## 8. 应用内的引导

Electron 应用的「新手引导」第 1 步就是本文档的简化版：

1. 「安装驱动」显示实时状态；点击「一键安装驱动」并授权 UAC（只需一次），高级区域保留 Zadig 手动方案
2. 按 `PLAY + AF-ON` 开机进服务模式；如第 1 步未检测到设备，应先完成此操作再回去安装
3. 「连接并验证」检查机身信息；驱动正常不等于相机通信已验证

如果这步失败，应用状态栏会显示「未连接」，请回到本文档第 6 节排查。
