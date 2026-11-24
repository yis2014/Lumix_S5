import { useState } from 'react';
import { Alert, Button, Card, Descriptions, Flex, Input, Space, Tag, Typography } from 'antd';
import { FolderOpenOutlined } from '@ant-design/icons';

export default function Settings({ device }) {
  const [feedback, setFeedback] = useState(null);
  const { env, locked } = device;
  async function choosePython() {
    const result = await device.pickPython();
    if (result) setFeedback(result);
  }
  return <Space orientation="vertical" size="large" className="full-width">
    <div><Typography.Title level={2}>设置</Typography.Title><Typography.Text type="secondary">管理本机运行环境与应用信息。</Typography.Text></div>
    <Card title="Python 运行环境" extra={<Tag color={env?.python ? 'blue' : 'default'}>{env?.mock ? '模拟环境' : env?.python ? '可用' : '未配置'}</Tag>}>
      <Space orientation="vertical" size="middle" className="full-width">
        <Typography.Text type="secondary">相机通信通过本地 Python 3 完成，无需安装额外 Python 包。</Typography.Text>
        <label htmlFor="pythonPath">当前 Python 路径</label>
        <Flex gap="small"><Input id="pythonPath" readOnly value={env?.python || '未找到 Python 3'} />
          <Button id="pickPython" icon={<FolderOpenOutlined />} disabled={locked || env?.mock} loading={device.configuring && !env?.mock} onClick={choosePython}>选择路径</Button></Flex>
        <Typography.Text type="secondary">Windows 选择 python.exe。路径保存在本机；模拟模式无需 Python。</Typography.Text>
        {feedback && <Alert id="settingsFeedback" showIcon type={feedback.ok ? 'info' : 'error'} title={feedback.ok ? 'Python 路径已保存，已重新检查设备。' : feedback.error} />}
      </Space>
    </Card>
    <Card title="关于 LumixTool" extra={<Tag>v{__APP_VERSION__}</Tag>}>
      <Descriptions column={1} items={[
        { key: 'camera', label: '当前支持', children: 'Panasonic DC-S5 · 28 项音效替换' },
        { key: 'mode', label: '运行方式', children: env?.mock ? '模拟模式 · 不访问相机' : '本地运行 · 离线' },
        { key: 'platform', label: '实机平台', children: 'Windows · WinUSB' },
        { key: 'theme', label: '外观', children: '跟随系统 · 浅色 / 深色' },
        { key: 'data', label: '设置目录', children: <Typography.Text className="break-text">{env?.userData || '正在检测…'}</Typography.Text> },
      ]} />
    </Card>
  </Space>;
}
