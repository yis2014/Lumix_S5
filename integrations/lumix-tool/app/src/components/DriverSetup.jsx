import { useState } from 'react';
import { Alert, Button, Checkbox, Collapse, Space, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { driverState } from './driverState.mjs';

const { Paragraph, Text } = Typography;

export function DriverStatus({ driver }) {
  const status = driverState(driver);
  return <Alert id="driverStatus" role="status" aria-live="polite" showIcon type={status.type} title={status.title}
    description={<Space orientation="vertical"><span>{status.description}</span>{driver?.driver && <Text type="secondary">驱动：{driver.driver}{driver.provider ? ` · ${driver.provider}` : ''}</Text>}{driver?.warning && <Text className="break-text">{driver.warning}</Text>}</Space>} />;
}

export default function DriverSetup({ device }) {
  const [removeCertificate, setRemoveCertificate] = useState(false);
  const [linkError, setLinkError] = useState('');
  const { driver, locked, driverChecking, busy } = device;
  const working = busy?.tool === 'driver';
  async function openZadig() {
    try {
      const result = await device.api.openZadig();
      setLinkError(result.ok ? '' : result.error);
    } catch (error) { setLinkError(error.message || String(error)); }
  }
  return <Space orientation="vertical" size="middle" className="full-width">
    <Paragraph>需要管理员权限，将安装一个本机自签名证书用于签名驱动，仅绑定 <Text code>04DA:2370</Text>（含接口 0）。证书加入本机「受信任的根证书颁发机构」与「受信任的发布者」，可在高级区域卸载时移除。</Paragraph>
    <Space wrap>
      <Button id="installDriver" type="primary" disabled={locked || !driver?.supported || driver?.ok} loading={working && busy.label === '正在安装驱动'} onClick={() => device.runDriver('install')}>一键安装驱动</Button>
      <Button id="recheckDriver" icon={<ReloadOutlined />} loading={driverChecking} disabled={locked || !driver?.supported} onClick={device.refreshDriver}>重新检测</Button>
    </Space>
    {working && <Alert showIcon type="info" title="等待管理员授权与驱动操作完成…" description="请处理 Windows UAC 弹窗。完成后会自动重新检测；期间请保持应用打开。" />}
    <Collapse items={[{ key: 'advanced', label: '高级', children: <Space orientation="vertical" size="middle" className="full-width">
      <Text>卸载仅删除 LumixTool 发布的驱动包。重新连接 USB，或普通开机恢复 04DA:2382 的系统 MTP 驱动。</Text>
      <Checkbox checked={removeCertificate} disabled={locked || !driver?.supported} onChange={event => setRemoveCertificate(event.target.checked)}>同时移除 LumixTool 本机签名证书（Root / TrustedPublisher / My）</Checkbox>
      <Button id="uninstallDriver" danger disabled={locked || !driver?.supported} loading={working && busy.label === '正在卸载驱动'} onClick={() => device.runDriver('uninstall', { removeCertificate })}>卸载驱动</Button>
      <Paragraph style={{ marginBottom: 0 }}>手动方式：<Button type="link" style={{ padding: 0 }} onClick={openZadig}>Zadig 官网</Button>。Options → List All Devices → 选择 04DA:2370（接口 0）→ WinUSB。请在设备管理器中验证 DeviceInterfaceGUIDs 为 <Text code>{'{CDE53111-593A-43C9-AB10-EA9DACF2C573}'}</Text>；详细步骤见 docs/DRIVER_SETUP.md。</Paragraph>
      {linkError && <Alert type="error" title={linkError} />}
    </Space> }]} />
  </Space>;
}

export function DriverResult({ device }) {
  const result = device.driverResult;
  if (!result) return null;
  const title = result.cancelled ? '已取消管理员授权，可重试'
    : !result.ok ? '驱动操作失败'
      : result.action === 'uninstall' ? 'LumixTool 驱动包已卸载'
        : device.driver?.ok ? '驱动正常，可以继续' : '驱动包已添加，请确认设备绑定';
  return <Alert showIcon type={result.ok ? 'success' : result.cancelled ? 'info' : 'error'} title={title}
    description={<Space orientation="vertical" className="full-width">
      <Text className="break-text">{result.message || result.error}</Text>
      {!result.ok && !result.cancelled && <Text>可展开「高级」使用 Zadig 手动安装。若 Windows 拒绝签名，请查看原始输出与 docs/DRIVER_SETUP.md。</Text>}
      {result.ok && result.action === 'install' && !device.driver?.ok && <Text>驱动包已添加不代表设备已切换到 WinUSB。请进入服务模式、重新插拔 USB 后重新检测；已有驱动的排名也可能阻止替换。</Text>}
      <Text type="secondary">步骤：{result.step || '未知'} · pnputil 退出码：{result.pnputilExit ?? '未运行'}</Text>
      {result.output && <Collapse className="full-width" items={[{ key: 'output', label: '查看原始输出', children: <pre className="break-text driver-output">{result.output}</pre> }]} />}
    </Space>} />;
}
