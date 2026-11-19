# DC-S5 V2.8 / V2.9：公开安全公告与入口证据审查

调查日期：2026-11-01（Asia/Shanghai）。对象：用户自有 Panasonic DC-S5；仅公开资料与现有上下文审阅。没有访问相机、SD 卡、USB 或 Wi-Fi 设备，没有生成或执行攻击载荷，也没有下载/刷写固件。

## 1. 结论

**发现直接对应 DC-S5 的安全维护说明，但本次公开检索未找到明确把 CVE 编号、漏洞入口及受影响版本同时绑定到 DC-S5 V2.8/V2.9 的公告。**

- [Panasonic DC-S5 官方更新记录](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/ff/dl/s5.html)明确：**V2.9，2025-07-29，"Enhanced the security of products."**；另有稳定性改善。这是实际 S5 的直接厂商证据，而不是其它机型类推。
- 同页 **V2.8，2024-10-09**：增加 Panasonic 伸缩镜头使用提示及稳定性改善。该页没有给出 CVE、漏洞类型、触发文件、USB/PTP 命令、Wi-Fi 服务、受影响版本上界或修复细节。
- 因而，**V2.9 有安全增强 ≠ V2.8 已证实存在代码执行漏洞；V2.9 有安全增强 ≠ V2.9 所有入口已排除漏洞。**
- 在已查询的 NVD 关键词结果及已读原始公告中，没有获得 S5 SD 文件解析、镜头升级、USB/PTP 或 Wi-Fi 任一入口的公开可利用性证据。
- Canon PTP CVE、Panasonic 安防网络摄像机/ActiveX 软件 CVE、IR Blaster 固件加载 CVE均为**排除误归属的对照项**，不是 S5 漏洞。

## 2. 本地上下文与证据级别

已读 [CONTINUE.md](../CONTINUE.md#L23-L44)：

1. S5 V2.8/V2.9 的 P-256 **元数据验签公钥已恢复并验证**；这不是 AES 解密密钥，也不是签名私钥。固件载荷解密 key 仍未恢复。
2. G100 的代码、地址、解析逻辑、密码实现及 rootfs 分析结果都带有机型限定；共同 OSS 页面不证明二进制、补丁级别、运行配置或执行路径相同。
3. 用户观察“修改镜头固件版本可进入刷写、但无可见效果”只证明进入某一检查/更新流程的现象。没有执行结果、控制流变化或内存证据，**不归类为代码执行、验签绕过成功或持久写入成功**。

主代理随后提供的 [S5 已验签分区差异](s5_v28_v29_authenticated_diff.json#L1-L27)已读取核对：V2.8/V2.9 均记录元数据验签成功；48 分区中只有 `program`、`postboot1`、`postboot3`、`postboot5`、`eep_fix`、`osdover`、`zimage`、`rootfs1`、`rootfs2` 的明文摘要变化。41 个密文/IV 变化不等于 41 个明文分区变化。这支持后续离线差异定位，但没有把任何分区绑定到具体 CVE，也没有提供解密 key。本子任务读取该结果，未重新执行其密码验证。

本报告分级：

- **A：实际 S5 直接证据**——官方明确列出 DC-S5 与版本/行为。当前只有更新说明和官方更新入口说明；没有已确认 S5 CVE。
- **B：同厂商其它产品/其它机型**——公告确实成立，但没有 S5 关联证据。
- **C：组件版本或代码迁移推测**——OSS 名称、G100 字符串、旧 Linux 版本等只形成待核验假设，不填写为 S5 受影响。
- **D：其它厂商对照**——Canon 等；共享 PTP 协议名称不意味着共享脆弱实现。

## 3. 实际 S5、镜头与介质入口：公开资料支持到哪里

| 入口/事项 | 原始来源与可确认内容 | S5 V2.8/V2.9 的证据边界 |
|---|---|---|
| V2.9 安全增强 | [DC-S5 更新记录](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/ff/dl/s5.html)，V2.9 / 2025-07-29 明确 security；下载名 `S5___V29.zip`，解压名 `S5___V29.bin` | **A**，确认版本和安全维护文字；CVE/入口/受影响区间未公开于此页 |
| SD 卡固件文件 | S5 更新页直接链接[官方更新流程](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/ff/step1.html)：内存卡根目录中的 `.bin` / `.plf`，由固件更新菜单处理 | 确认支持的更新输入通道；不证明畸形文件解析缺陷。通用流程也提 CFexpress，不据此声称 S5 支持 CFexpress |
| 镜头固件升级 | 同一[更新流程](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/ff/step1.html)要求装上镜头；[L-mount 镜头索引](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/index5.html)列出 Panasonic 机身更新 Panasonic/LEICA/SIGMA 镜头的组合 | 证明镜头升级是正常产品功能；没有公告证明任意镜头文件进入机身执行或绕过验证 |
| 镜头样例 | [S-R2060 官方更新记录](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/ff/dl/r2060.html)：V2.0 / 2025-05-14，`400BV020.plf`，新增对焦环功能；V1.1 的兼容说明明确写 DC-S5M2 | 只检查这一具体镜头更新页作为样例，未逐一审完所有镜头；**DC-S5M2 不等于 DC-S5**；未见 CVE/安全漏洞说明 |
| USB | [官方更新流程](https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/ff/step1.html)描述 USB `PC(Storage)` 向卡复制更新文件；实际更新阶段提示断开 USB/HDMI、取消无线连接 | USB 拷贝路径不是 PTP 任意内存读写或 USB 直接执行升级证据；本轮没有设备协议验证 |
| Wi-Fi / Bluetooth | S5 更新历史有连接质量/冻结稳定性说明；当前检查的记录未把 V2.9 security 指向某个无线服务 | 稳定性修复不自动等于安全漏洞；没有已确认 S5 无线 CVE，未把 Canon PTP/IP 实现迁移到 S5 |

上述官方流程仅用作入口存在性证据，本报告没有执行这些操作。

## 4. 明确 CVE 与原始公告：逐项排除误归属

**下表全部没有实际 S5 V2.8/V2.9 受影响证据。** “其它产品”表示已核对公告列名，不表示已实测 S5 不受影响。

| CVE | 原始公告 URL | 公告中的受影响产品/版本及前提 | S5 证据/归类 |
|---|---|---|---|
| **CVE-2008-3482** | [JVN33706820](https://jvn.jp/en/jp/JVN33706820/index.html) | Panasonic BL-C111 ≤3.14R02、BL-C131 ≤3.14R03、BB-HCM511/531/515 ≤3.20R01、BB-HCM580/581 ≤3.21R00、BB-HCM527 ≤3.30R00；错误页面 XSS，浏览器用户交互 | 无；**B：安防网络摄像机**，非 LUMIX。版本范围优先用 JVN 原文，NVD 的个别 CPE 标注有差异 |
| **CVE-2014-8755** | [ZDI-14-364](https://www.zerodayinitiative.com/advisories/ZDI-14-364/) | Panasonic Network Camera View 3/4（版本来自 NVD）；WebVideoCam ActiveX 控件，用户访问恶意页面或打开文件 | 无；**B：PC 浏览器控件**。ZDI 明确需要用户交互，优先于旧 NVD 不一致的 UI 字段 |
| **CVE-2014-8756** | [ZDI-14-363](https://www.zerodayinitiative.com/advisories/ZDI-14-363/) | Panasonic Network Camera Recorder <4.04R03（版本来自 NVD）；ActiveX 控件，用户访问页面/打开文件 | 无；**B：PC 软件**，不是相机 SD 解析 |
| **CVE-2015-4647** | [ZDI-15-259](https://www.zerodayinitiative.com/advisories/ZDI-15-259/) | Panasonic Security API ActiveX SDK <8.10.18（版本来自 NVD）；控件字符串处理，用户访问页面/打开文件 | 无；**B：安防 SDK**。`Panasonic SD` 查询命中的是 SDK 字样，不是 SD 卡证据 |
| **CVE-2015-4648** | [ZDI-15-261](https://www.zerodayinitiative.com/advisories/ZDI-15-261/) | 同一 Security API ActiveX SDK <8.10.18；控件字符串处理与用户交互 | 无；**B：安防 SDK**，不是 S5 固件 |
| **CVE-2014-9596** | [CERT/CC VU#117604](https://www.kb.cert.org/vuls/id/117604/)；CVE 关联由 [NVD 查询](https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch=Panasonic%20USB&resultsPerPage=100)确认 | Arbitrator BES MK2 VPU <9.3.1 build 4.08.003.0，USB Wi-Fi/Direct LAN；MK3 <9.3.1 build 5.06.000.0，Embedded Wi-Fi/Direct LAN；网络通信明文泄露。版本来自 NVD | 无；**B：Arbitrator 系统**。CERT 原页 CVE 栏为 None，不伪称它自身列出了该 CVE |
| **CVE-2022-4621** | [CISA ICSA-23-012-04](https://www.cisa.gov/news-events/ics-advisories/icsa-23-012-04)；[原厂归档 URL](https://archives.connect.panasonic.com/security/sanyo/index.html)本次 404 | Sanyo CCTV：VCC-HD5600P 2.03-06；VDC-HD3300P 2.03-08 / 1.02-05；VCC-HD3300 2.03-02；VDC-HD3100P 2.03-00；VCC-HD2100P 2.03-02。HTTP CSRF 导致管理员级更改；CISA 与 NVD 的 UI 评分不同 | 无；**B：Sanyo 安防摄像机**，非 DC-S5 |
| **CVE-2025-1073** | [厂商 release notes](https://lsin.panasonic.com/release-notes)（HTTP200，但抓取正文为空）；[含 Panasonic CNA 原文的 NVD 记录](https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-2025-1073) | Panasonic IR Control Hub / IR Blaster **≤1.17**；需要物理接触，涉及加载非预期固件 | 无；**B：红外控制 Hub**。厂商页正文未核验，产品/前提根据 Panasonic CNA 数据；不是 S5 镜头升级 CVE |
| **CVE-2019-5994** | [JVNVU97511331](https://jvn.jp/en/vu/JVNVU97511331/index.html)；[Check Point 原始研究](https://research.checkpoint.com/2019/say-cheese-ransomware-ing-a-dslr-camera/) | Canon EOS / 指定 PowerShot 的 PTP `SendObjectInfo` 溢出；研究实机 EOS 80D，NVD 对 EOS 80D 列 ≤1.0.2；前提为可达受影响 PTP 通道（USB 连接或适用网络模式） | 无；**D：Canon**。协议名相同不足以迁移漏洞 |
| **CVE-2019-5998** | [JVNVU97511331](https://jvn.jp/en/vu/JVNVU97511331/index.html) | Canon 上述产品族中的 `notifybtstatus` PTP 处理问题；具体机型/版本按各条官方矩阵；需要可达该实现 | 无；**D：Canon** |
| **CVE-2019-5999** | [JVNVU97511331](https://jvn.jp/en/vu/JVNVU97511331/index.html) | Canon 上述产品族中的 `blerequest` PTP 处理问题；同样需匹配具体型号/固件与通道 | 无；**D：Canon** |
| **CVE-2019-6000** | [JVNVU97511331](https://jvn.jp/en/vu/JVNVU97511331/index.html) | Canon 上述产品族中的 `sendhostinfo` PTP 处理问题；同样需匹配具体型号/固件与通道 | 无；**D：Canon** |
| **CVE-2019-6001** | [JVNVU97511331](https://jvn.jp/en/vu/JVNVU97511331/index.html) | Canon 上述产品族中的 `setadapterbatteryreport` PTP 处理问题；同样需匹配具体型号/固件与通道 | 无；**D：Canon** |
| **CVE-2019-5995** | [JVNVU97511331](https://jvn.jp/en/vu/JVNVU97511331/index.html) | Canon EOS / 指定 PowerShot 固件升级缺少用户确认/授权检查；不是“所有厂商固件签名均可绕过”的公告 | 无；**D：Canon**。尤其不支持将 S5 修改版本后进入界面的观察解释为此 CVE |

Canon JVN 的产品范围为 EOS 系列及 PowerShot SX70HS、SX740HS、G5XMarkII；各 CVE 的逐机型版本矩阵并未在本轮全部展开，未用 5994 的版本界限套用其它五条。Canon 原厂欧洲安全入口本次 403，日本原厂公告抓取失败；原始研究和 JPCERT 协调公告成功读取。这些访问限制保留于来源 JSON。

## 5. 组件版本推测单列：没有“旧库即 S5 漏洞”的结论

[Panasonic 官方 OSS 页面](https://ospo.panasonic.com/oss/dsc/DC-FZ1K2.html)明确同时列出 DC-S5、DC-G100 等，并链接 Linux 3.18.18、glibc、bash 等源码。

这是 **S5 的 OSS 分发关联证据**，不是 S5 V2.8/V2.9 的精确 SBOM、运行二进制版本证明或 CVE 受影响声明。库名/源码包版本到实际 S5 漏洞，至少还差：

1. S5 特定固件的真实编译版本、厂商回移补丁状态与配置；
2. 相关脆弱函数确实包含在运行代码中；
3. SD/镜头/USB/Wi-Fi 输入实际到达该函数的证据；
4. 前提与公告一致，而不只是 G100 可见同名函数。

因此本轮**不列任何仅依赖旧 Linux/glibc/bash 版本猜测的 CVE 为 S5 候选漏洞**。`Panasonic` NVD 搜索还包含 x86 笔记本驱动、MINAS Windows USB 驱动、PLC/手机漏洞；它们与 ARM 相机不是同一产品。

## 6. 检索范围、失败与负面结论限定

技能目录先检查：只有 Windows sandbox ACL 和 Office 系列，没有匹配的固件/漏洞公告调查技能。使用 web_search / web_fetch；首次 web_search 返回缺 `DEEPSEEK_API_KEY`，未反复重试。随后直接访问 NVD、厂商支持页、JPCERT/JVN、ZDI、CERT/CC、CISA 与原始研究 URL。Shell 只用于把公开页面/结果归档及校验文件，不连接设备。

| NVD API `keywordSearch` 实际查询 | 返回条目数 | 本次解释 |
|---|---:|---|
| `Panasonic` | 39 | 读取全部 39 条描述与引用索引，未见 LUMIX/DC-S5；并非全互联网覆盖 |
| `LUMIX` | 0 | 该关键词在本次 API 返回中无结果 |
| `DC-S5` | 0 | 同上，不排除其它命名、未登记 CVE 或未公开问题 |
| `lens firmware` | 0 | 仅此关键词组合，非所有镜头或镜头供应商全量审计 |
| `Panasonic camera` | 4 | 网络摄像机/相关 PC 软件；不是 S5 |
| `Panasonic SD` | 2 | ActiveX SDK 结果；不是卡文件解析证据 |
| `Panasonic USB` | 1 | Arbitrator BES 的 USB Wi-Fi 语境；不是 S5 USB。关键词结果不替代全量产品/CPE 筛选 |

成功读取：DC-S5 更新记录、数码相机支持首页、L-mount 镜头索引、S-R2060 更新记录、通用更新流程、OSS 页面，以及表中协调/研究公告。

受限来源：Panasonic 公司级 PSIRT 两个入口均 403；猜测的通用 security 页 404；Sanyo 厂商旧归档 404；Canon 原厂页如上；IR Blaster release notes 抓取正文为空。镜头详情首次猜测 URL 404，随后从真实索引 HTML 的 `OpenWinS12` 链接解析到正确 `r2060.html`，HTTP200；没有把 404 当负面漏洞结论。

**限定性负面结论：截至本次调查，在以上实际查询与实际读取页面范围内，未找到已公开且明确适用于 DC-S5 V2.8/V2.9 的 SD 解析、镜头更新、USB/PTP 或 Wi-Fi CVE。** 这不证明不存在漏洞，也不证明厂商从未发布其它公告。最有价值的公开新证据是 **S5 V2.9 的明确 security 更新文字，但没有公开映射的 CVE/修复入口**。

## 7. 产物与后续证据门槛

- [结构化来源及结论](public_advisories_sources.json)：URL、HTTP/失败状态、关键摘录、适用性、检索计数与本地上下文。
- [NVD Panasonic 39 条索引](sources/nvd_panasonic_index.json)：保留 CVE/描述/引用；两条无关网络摄像机记录的凭据及请求字节已替换为非操作性摘要，不是逐字原始镜像。
- [S5 官方更新页快照](sources/s5_vendor_updates.html)：SHA-256 `497e79f18676f4acc52faf6dbfe9696b970badc64f723ae9b19ea87c22b50897`。
- [镜头官方索引快照](sources/lens_vendor_index.html)：SHA-256 `ec51d1d0be90f3d95e809a234aa7b1d7f06373828e55762cab36ac7dc7823ce0`。

后续离线工作若需要把公开线索升级为 S5 结论，应优先补上 S5 V2.8→V2.9 的具体安全更改说明/真实二进制对应关系、确切库与补丁状态、输入到处理函数的可达性证据。现有验签公钥只支持验证元数据，不直接补齐解密 key 或执行入口。
