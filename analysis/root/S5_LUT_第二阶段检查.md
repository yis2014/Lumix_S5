# DC-S5 实时 LUT 烧录：第二阶段只读检查

## 目标与结果

目标限定为相机编码前应用用户导入的 LUT，使 SD 卡视频自带效果；不是监看、外录或导出后处理。

本轮实际检查两份机身固件的41个标志3载荷区、摘要和附加字段，以及公开解析/加密/加载研究。没有找到可读程序、可靠解密方法或可用于LUT补丁的执行入口，因此**尚未实现机内实时LUT烧录，也没有生成可刷固件**。没有修改原固件，没有连接或向实体相机发命令。

## 本地测试

脚本：[probe_payload.py](../probe_payload.py)

完整结果：[payload_probe.json](payload_probe.json)

### 1. 附加16字节字段

对两版本的全部48项分别验证：该字段是否等于对应原始分区数据的MD5、SHA-256前16字节或后16字节。

结果：均未匹配。这排除了本次测试的三种直接摘要解释，不证明字段一定是IV、nonce或密钥。

### 2. 简单编码检查

- 对所有标志3区做2/4/8/16字节组内字节反转，再核对目录SHA-256字段。
- 对不超过64KiB的标志3区穷举256种固定单字节XOR，再核对目录SHA-256字段。

结果：无匹配。这里只排除这些具体变换可直接得到目录摘要输入的情况；不是穷举加密方案，也没有假设目录摘要对标志3必然等于明文SHA-256。

### 3. 相同摘要载荷对照

跨版本及同包内找到40对大小与目录摘要相同的标志3区：

- 原始载荷没有任何一对完全相同。
- 对每对前至多64KiB求逐字节XOR，未出现1/2/4/8/16/32/64/128/256字节周期。
- XOR样本熵约7.8998至7.9976 bits/byte。

这不支持用固定短周期XOR差值直接还原两版；也不能因此确定AES-CTR、密钥长度或是否存在其他攻击方式。

### 4. 可读字符串

在正确物理边界内扫描长度至少12的可打印ASCII串，共770条，最长18字符。检索这些长串中的Panasonic、VLog、V-Log、.vlt、LUT、Linux、ThreadX，均无命中。最长串表现为无语义的混合字符，不能当作已找到代码或资源。

此前全包短串中的偶然LUT命中不构成功能定位。本轮没有执行反汇编器：在未获得明文及指令集证据前，把随机载荷强制反汇编会产生误导性的伪指令。

## 公开研究核查

### 现代全画幅研究项目

仓库：[ShaoCI-Hz/lumix-fullframe-reverse](https://github.com/ShaoCI-Hz/lumix-fullframe-reverse)

本轮检查版本：`62d77cb5a63db6e9f098ee4065d409d5cb4d461e`。

- 本次查询时仅main分支，没有公开issue/PR中的新增解密成果。
- [pana_unpack.py](https://raw.githubusercontent.com/ShaoCI-Hz/lumix-fullframe-reverse/62d77cb5a63db6e9f098ee4065d409d5cb4d461e/tools/pana_unpack.py)仅作解析/统计/切片，且误把目标地址字段当包内偏移；不能直接用其提取结果判断明文或结构。
- [crypto_signature.py](https://raw.githubusercontent.com/ShaoCI-Hz/lumix-fullframe-reverse/62d77cb5a63db6e9f098ee4065d409d5cb4d461e/analysis/body/crypto_signature.py)对64字节候选做整数范围等测试，没有公钥验签。此测试不足以证明ECDSA或签名覆盖范围。
- [MTP协议记录](https://raw.githubusercontent.com/ShaoCI-Hz/lumix-fullframe-reverse/62d77cb5a63db6e9f098ee4065d409d5cb4d461e/docs/en/05-mtp-vendor-protocol.md)涉及S5M2X，不是原代S5的运行时dump/执行验证。读取上下文返回成功但数据长度为零，不是RAM读取入口；写入部分仍未实现。

限定：本轮没有逐文件审完仓库全部脚本，也未穷尽全网，不能宣布绝无入口。

### 独立UPD布局旁证

[FT5/TS5/TZ40解析器](https://raw.githubusercontent.com/unaialberdi22/Lumix-FT5-reverse-engineering-proyect/main/lumix_upd.py)独立采用0x2EC目录、12字节名称、physical offset/size/load address/flags及32+16字节字段的结构，与本地已验证的S5布局一致。它明确不解密、密钥未知，而且只测过老机型，不能据此得到S5解密能力。

本轮公开研究受GitHub API限流与未认证代码搜索限制影响。结论是“核查范围内未见已验证的MC801解密/加载链”，不是证明全网不存在。

## 相机连接能提供什么

暂时不需要连接，因为现有固件检查不依赖实体设备。

- 读卡/大容量存储：通常仅暴露存储卡，不提供机身程序或图像处理内存。
- PTP/MTP/遥控模式：可能提供设备描述与厂家扩展操作，但协议操作存在不等于支持内存读取；其他机型操作码不能盲发到S5。
- 连接后的第一步最多应是只读枚举设备、接口、VID/PID与协议模式，再判断是否有研究价值；不自动尝试服务模式、厂商写命令、升级、降级或内存访问。
- 物理flash/串口需要先识别硬件、接口电平、加密存储状态与恢复方式。读出flash也可能仍是密文，不能保证拆机就解决。

## 距离实现还缺什么

至少需要获得一条有证据的可读程序路径：

1. 包内载荷的真实解密/解码算法及所需参数；或
2. 对原代S5确实可用的合法运行时代码读取入口；或
3. 未加密的可信程序/服务资料，可定位升级器与图像管线。

随后才能追踪 VLT 加载→监看LUT配置→录像编码输入，判断是开放已有节点还是重构路径。还必须独立解决修改程序加载与恢复验证。

目前不能给出LUT补丁地址，也不能估算“几天可完成”。继续盲猜AES密钥或修改CRC/版本字段不会构成可靠实现。
