import { useEffect, useState } from 'react';
import { Alert, Button, Card, Flex, Space, Steps, Typography } from 'antd';
import { ArrowRightOutlined, CameraOutlined, ReloadOutlined, UsbOutlined } from '@ant-design/icons';
import DriverSetup, { DriverResult, DriverStatus } from './DriverSetup';

const { Paragraph, Text, Title } = Typography;
const steps = [
  { title: '安装驱动', content: 'WinUSB' },
  { title: '进入临时服务模式', content: 'P档·单拍·回放+AF ON' },
  { title: '连接并验证', content: 'USB · 04DA:2370' },
];

export default function ConnectionGuide({ device, navigate, active }) {
  const [step, setStep] = useState(0);
  const { ready, actionLocked, checking, device: camera } = device;
  useEffect(() => {
    if (device.driver?.ok) setStep(current => current === 0 ? 1 : current);
    else if (device.driver?.present) setStep(0);
  }, [device.driver?.ok, device.driver?.present]);
  useEffect(() => {
    if (!active || !device.driver?.supported) return;
    const timer = setInterval(() => { void device.refreshDriver(); }, 5000);
    return () => clearInterval(timer);
  }, [active, device.driver?.supported, device.refreshDriver]);
  return (
    <Space orientation="vertical" size="large" className="full-width">
      <div><Title level={2}>连接你的 LUMIX</Title><Text type="secondary">首次连接需要 Windows、USB 数据线与 WinUSB 驱动。</Text></div>
      <Card><Steps current={step} onChange={setStep} items={steps.map((item, index) => index === 0 && device.driver?.ok ? { ...item, status: 'finish' } : index === 0 && step > 0 ? { ...item, status: 'wait' } : item)} /></Card>
      <DriverStatus driver={device.driver} />
      <DriverResult device={device} />
      <Card title={<Space>{step === 0 ? <UsbOutlined /> : <CameraOutlined />}{steps[step].title}</Space>}>
        {step === 0 && <>
          <DriverSetup device={device} />
        </>}
        {step === 1 && <>
          <Title level={4}>右转轮调到 P 档，左转轮调到单拍，同时按住回放 + AF ON 开机</Title>
          <Paragraph>先将 DC-S5 关机，把<strong>右转轮调到 P 档</strong>、<strong>左转轮调到单拍</strong>，再同时按住以下两个按键打开相机电源，进入临时服务模式。</Paragraph>
          <Paragraph><Text keyboard>右转轮 P 档</Text> ＋ <Text keyboard>左转轮 单拍</Text> → 按住 <Text keyboard>回放 (PLAY)</Text> ＋ <Text keyboard>AF ON</Text> → <Text strong>打开电源</Text></Paragraph>
          <Alert showIcon type="warning" style={{ marginBottom: 12 }} title="必须先调好左右转轮" description="若右转轮不在 P 档或左转轮不在单拍，开机后会一直被识别成其他模式（如普通模式 04DA:2382），无法进入临时服务模式。" />
          <Alert showIcon type="info" title="保留电池供电" description="写入完成后需要通过电源键关机再开机，让音效生效。不要拔电池。" />
        </>}
        {step === 2 && <>
          <Title level={4}>连接 USB，检查相机</Title>
          <Paragraph>将相机连接到电脑，确认服务模式标识为 <Text code>04DA:2370</Text>。关闭其他占用相机的程序，再检查连接。</Paragraph>
          <Alert showIcon type={camera.error ? 'warning' : 'info'}
            title={ready ? `已连接 LUMIX ${camera.model || 'DC-S5'} · 机身版本 ${camera.body_version || '未知'}` : checking ? '正在检测设备…' : '等待设备连接'}
            description={ready ? '设备已就绪，可以开始使用相机工具。' : camera.error || camera.platformNote || '准备好后，点击下方按钮检查设备。'} />
        </>}
        <Flex justify="space-between" className="section-actions">
          <Button disabled={step === 0} onClick={() => setStep(step - 1)}>上一步</Button>
          {step < 2 ? <Button type="primary" onClick={() => setStep(step + 1)}>下一步<ArrowRightOutlined /></Button>
            : <Button id="verifyDevice" type="primary" loading={checking} disabled={actionLocked} icon={ready ? <ArrowRightOutlined /> : <ReloadOutlined />}
              onClick={() => ready ? navigate('focus-sound') : device.refreshDevice()}>{ready ? '开始使用工具' : '检查连接'}</Button>}
        </Flex>
      </Card>
      <Text type="secondary">未能识别？确认右转轮在 P 档、左转轮在单拍并按住回放 + AF ON 开机进入临时服务模式（否则会一直识别成其他模式），检查 WinUSB 驱动，关闭其他相机软件，或更换 USB 端口。macOS / Linux 可使用模拟模式开发。</Text>
    </Space>
  );
}
