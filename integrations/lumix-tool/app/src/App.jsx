import { Alert, Badge, Button, Checkbox, Flex, Layout, Menu, Select, Space, Tag, Typography, theme } from 'antd';
import { CameraOutlined, ExperimentOutlined, ReloadOutlined, SettingOutlined, UsbOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { useDevice } from './hooks/useDevice';
import { tools } from './tools';
import ConnectionGuide from './components/ConnectionGuide';
import Settings from './components/Settings';
import { needsDriverSetup } from './components/driverState.mjs';

const { Header, Sider, Content, Footer } = Layout;
const { Text, Title } = Typography;

export default function App() {
  const device = useDevice(window.api);
  const [page, setPage] = useState(tools[0].id);
  const { token } = theme.useToken();
  const { env, ready, locked, checking, busy, device: camera } = device;
  const missing = camera.pythonMissing || (env && !env.python);
  const driverNeeded = needsDriverSetup(device.driver);
  const label = busy ? busy.label : checking || !env ? '检测中' : missing ? '需要 Python' : camera.error ? '连接异常' : ready ? '已连接' : '未连接';
  const statusColor = busy || checking ? token.colorPrimary : camera.error && !missing ? token.colorError : ready ? token.colorPrimary : token.colorTextQuaternary;
  const selectedTool = tools.find(tool => tool.id === page);
  const menuItems = [
    { type: 'group', label: '相机工具', children: tools.map(tool => ({ key: tool.id, icon: tool.icon, label: tool.title, 'data-tool': tool.id })) },
    { type: 'divider' },
    { key: 'connection', id: 'navConnection', icon: <UsbOutlined />, label: '连接指南' },
    { key: 'settings', id: 'navSettings', icon: <SettingOutlined />, label: '设置' },
  ];

  return <Layout className="app-shell" style={{ minHeight: '100vh' }}>
    <Sider width={216} theme="light" style={{ background: token.colorBgContainer, borderRight: `1px solid ${token.colorBorderSecondary}` }}>
      <Flex vertical className="sidebar-content">
        <Flex align="center" gap="small" className="brand"><CameraOutlined style={{ color: token.colorPrimary, fontSize: 26 }} /><div><Title level={4} style={{ margin: 0 }}>LumixTool</Title><Text type="secondary">LUMIX 相机工具箱</Text></div></Flex>
        <Menu mode="inline" selectedKeys={[page]} items={menuItems} onClick={({ key }) => setPage(key)} style={{ borderInlineEnd: 0 }} />
        <div className="sidebar-footer"><Text type="secondary">本地运行 · 无需网络</Text><br /><Text type="secondary">v{__APP_VERSION__}</Text></div>
      </Flex>
    </Sider>
    <Layout style={{ minWidth: 0 }}>
      <Header className="device-header" style={{ background: token.colorBgContainer, borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
        <Flex align="center" gap="middle" justify="space-between" className="full-width">
          <Flex align="center" gap="middle" style={{ minWidth: 0 }}>
            <CameraOutlined style={{ fontSize: 24, color: token.colorTextSecondary }} />
            <div><Text strong id="deviceModel">LUMIX {camera.model || 'DC-S5'}</Text><br />
              <Text id="deviceDetail" type="secondary">{ready ? `服务模式 · 机身版本 ${camera.body_version || '未知'} · ${camera.custom ? '自定义音效' : '原厂音效'}` : driverNeeded ? 'USB 04DA:2370 · 请先安装驱动' : 'USB 04DA:2370 · 服务模式'}</Text></div>
          </Flex>
          <Space><Tag id="connectionState" color={camera.error && !missing ? 'error' : ready || busy ? 'blue' : 'default'}><Badge color={statusColor} text={<span id="connectionLabel">{label}</span>} /></Tag>
            <Button id="refreshDevice" aria-label="刷新设备连接" title="刷新设备连接" icon={<ReloadOutlined />} loading={checking} disabled={locked} onClick={device.refreshDevice} /></Space>
        </Flex>
      </Header>
      <Content className="workspace">
        <div className="page-content">
          {env?.mock && <MockToolbar device={device} />}
          {device.error && <Alert type="error" showIcon title={device.error} className="page-notice" />}
          {selectedTool && <>
            <Flex justify="space-between" align="center" gap="middle" className="page-heading"><div><Title level={2}>{selectedTool.title}</Title><Text type="secondary">{selectedTool.description}</Text></div><Tag>{selectedTool.scope || 'LUMIX'}</Tag></Flex>
            {!ready && !checking && env && <Alert className="page-notice" showIcon type={camera.error && !missing ? 'warning' : 'info'}
              title={driverNeeded ? '服务模式设备已连接，请先安装驱动' : missing ? '先准备 Python 运行环境' : camera.error ? '相机连接需要检查' : '先连接你的相机'}
              description={<span className="break-text">{driverNeeded ? '打开连接指南，使用「一键安装驱动」，完成后重新检测。' : camera.error || camera.platformNote || '进入服务模式并连接 USB，即可写入音效。你可以先选择音频并试听。'}</span>}
              action={<Button onClick={() => setPage(!driverNeeded && missing ? 'settings' : 'connection')}>{driverNeeded ? '安装驱动' : missing ? '打开设置' : '连接指南'}</Button>} />}
          </>}
          {tools.map(({ id, component: Tool }) => <section key={id} hidden={page !== id} data-tool-view={id}><Tool device={device} active={page === id} navigate={setPage} /></section>)}
          <section hidden={page !== 'connection'}><ConnectionGuide device={device} navigate={setPage} active={page === 'connection'} /></section>
          <section hidden={page !== 'settings'}><Settings device={device} /></section>
        </div>
      </Content>
      <Footer style={{ padding: '12px 28px', borderTop: `1px solid ${token.colorBorderSecondary}` }}>
        <Flex justify="space-between"><Text type="secondary">{busy ? `${busy.label} · 请保持 USB 与电源连接` : env?.mock ? '模拟模式 · 不访问相机' : '本地运行 · 无需网络'}</Text><Text type="secondary">LumixTool</Text></Flex>
      </Footer>
    </Layout>
  </Layout>;
}

function MockToolbar({ device }) {
  const { env, locked } = device;
  return <Flex className="mock-toolbar" align="center" justify="space-between" gap="middle" wrap>
    <Space><ExperimentOutlined /><Text strong>模拟模式</Text><Text type="secondary">所有操作均在本地模拟</Text></Space>
    <Space wrap><label htmlFor="mockScenario">设备状态</label><Select id="mockScenario" value={env.mockState.scenario} disabled={locked} style={{ width: 170 }}
      onChange={scenario => device.configureMock({ scenario })} options={[
        { value: 'connected', label: '已连接' }, { value: 'disconnected', label: '未连接' },
        { value: 'error', label: '连接异常' }, { value: 'python-missing', label: 'Python 缺失' },
        { value: 'region-not-free', label: '缓存过期（首个区域被占用）' },
        { value: 'unverified', label: '未验证固件（0x0280）' },
      ]} /><label htmlFor="mockDriver">驱动状态</label><Select id="mockDriver" value={env.mockState.driverScenario} disabled={locked} style={{ width: 170 }}
      onChange={driverScenario => device.configureMock({ driverScenario })} options={[
        { value: 'ok', label: '驱动正常' }, { value: 'absent', label: '无服务模式设备' }, { value: 'normal', label: '普通模式 2382' },
        { value: 'missing', label: '未安装驱动' }, { value: 'wrong-driver', label: '错误驱动 libusbK' },
        { value: 'missing-guid', label: '接口 GUID 缺失' }, { value: 'unknown-guid', label: '接口 GUID 未知' },
      ]} /><label htmlFor="mockDriverResult">驱动操作结果</label><Select id="mockDriverResult" value={env.mockState.driverResult} disabled={locked} style={{ width: 150 }}
      onChange={driverResult => device.configureMock({ driverResult })} options={[
        { value: 'success', label: '安装 / 卸载成功' }, { value: 'failure', label: '安装 / 卸载失败' }, { value: 'cancelled', label: '取消 UAC 授权' },
      ]} /><Checkbox id="mockFail" checked={env.mockState.failNext} disabled={locked} onChange={event => device.configureMock({ failNext: event.target.checked })}>下次相机操作失败</Checkbox></Space>
  </Flex>;
}
