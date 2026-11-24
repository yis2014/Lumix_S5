import { useState } from 'react';
import { Alert, Button, Card, Descriptions, Empty, Flex, Progress, Space, Table, Tag, Tooltip, Typography, theme } from 'antd';
import { DownloadOutlined, ScanOutlined } from '@ant-design/icons';
import { BLOCK, END, KINDS, START, hexAddress, liveRegions, markRange, memoryStats } from '../../../memory.mjs';

const { Text, Paragraph } = Typography;
const names = { 'free-0x55': '空闲（0x55）', lumixtool: 'LumixTool', data: '其他数据', zero: '全零' };

export default function Memory({ device }) {
  const { token } = theme.useToken();
  const [feedback, setFeedback] = useState(null);
  const [exporting, setExporting] = useState(false);
  const { api, ready, locked, progress } = device;
  const map = device.device.memoryMap;
  const entries = device.device.soundTable?.entries || [];
  const live = liveRegions(entries);
  const stats = memoryStats(map, entries);
  const colors = { 'free-0x55': token.colorSuccess, lumixtool: token.colorPrimary, data: token.colorTextQuaternary, zero: token.colorWarning };
  const scanning = device.busy && progress?.phase === 'scan';
  // Overlay current table ownership: a scan only recognizes the header block,
  // while dump identifies the full live PCM span.
  const displayMap = map && live.reduce((current, region) => markRange(current, region.start, region.end, 'lumixtool'), map);

  async function scan() {
    setFeedback(null);
    try {
      const result = await device.runOperation({ tool: 'memory', label: '正在扫描内存（只读）', execute: () => api.scanMemory() });
      setFeedback(result.ok ? { ok: true, text: '只读扫描完成，内存地图已更新。' } : { ok: false, text: result.error || '扫描失败，请检查连接后重试。' });
    } catch (error) { setFeedback({ ok: false, text: error.message || String(error) }); }
  }

  async function exportMap() {
    setExporting(true);
    try {
      const result = await api.exportMemory(map.bodyVersion);
      if (!result.canceled) setFeedback({ ok: result.ok, text: result.ok ? '内存扫描 JSON 已导出。' : result.error });
    } catch (error) { setFeedback({ ok: false, text: error.message || String(error) }); }
    finally { setExporting(false); }
  }

  const columns = [
    { title: '起始地址', dataIndex: 'start', render: value => <Text code>{value}</Text> },
    { title: '结束地址（不含）', dataIndex: 'end', render: value => <Text code>{value}</Text> },
    { title: '大小', dataIndex: 'kib', render: value => `${value.toLocaleString()} KiB` },
    { title: '类型', dataIndex: 'kind', render: kind => <Tag color={colors[kind]}>{names[kind]}</Tag> },
  ];
  return <Space orientation="vertical" size="large" className="full-width">
    <Alert showIcon type="info" title="只读诊断，不会写入相机" description="扫描 RAM 暂存区，每次读取 1 KiB。空闲状态可能随相机运行或拔电池变化；音效写入前还会再次检查目标字节。" />
    <Card title="内存扫描" extra={<Space>
      <Button id="scanMemory" type="primary" icon={<ScanOutlined />} disabled={!ready || locked || exporting} loading={!!scanning} onClick={scan}>扫描内存</Button>
      <Button id="exportMemory" icon={<DownloadOutlined />} disabled={!map || locked || exporting} loading={exporting} onClick={exportMap}>导出 JSON</Button>
    </Space>}>
      <Descriptions column={2} size="small" items={[
        { key: 'time', label: '上次扫描', children: map ? new Date(map.scannedAt).toLocaleString('zh-CN') : '尚未扫描' },
        { key: 'body', label: '机身版本', children: map?.bodyVersion || device.device.body_version || '—' },
      ]} />
      {scanning && <div role="status"><Text>正在只读扫描 RAM…</Text><Progress percent={Math.min(100, Math.round(progress.done / progress.total * 100))} status="active" /><Text type="secondary">{progress.done.toLocaleString()} / {progress.total.toLocaleString()} KiB</Text></div>}
      {feedback && <Alert className="page-notice" showIcon type={feedback.ok ? 'success' : 'error'} title={feedback.text} />}
      {!map && <Paragraph type="secondary">扫描范围 {hexAddress(START)}–{hexAddress(END)}（{((END - START) / 1048576).toFixed(2)} MiB）。模拟扫描约 3 秒，实机扫描时间以进度为准。</Paragraph>}
    </Card>
    <Card title="空间概览">
      <Descriptions column={{ xs: 1, sm: 2, xl: 3 }} items={[
        ['free', '可写入空间', stats.totalFree], ['largest', '最大连续可写入', stats.largestFree],
        ['used', 'LumixTool 当前使用', stats.used], ['data', '其他数据', stats.data], ['zero', '全零', stats.zero],
      ].map(([key, label, value]) => ({ key, label, children: map || key === 'used' ? `${(value / BLOCK).toLocaleString()} KiB` : '—' }))} />
      <Paragraph type="secondary">当前使用量来自音效表，结束地址向上取整到 1 KiB。可写入空间包括空闲（0x55）、全零和其他数据区段（暂存区热重启后会残留旧数据，残留数据可以覆盖），只排除 LumixTool 当前占用的区域。</Paragraph>
      <Space wrap>{KINDS.map(kind => <Space key={kind}><span className="memory-legend" style={{ background: colors[kind] }} /><Text>{names[kind]}</Text></Space>)}</Space>
      <div id="memoryMap" className="memory-map" role="img" aria-label="RAM 暂存区内存分布" style={{ background: token.colorFillSecondary }}>
        {displayMap?.runs.map(item => <Tooltip key={item.start} title={`${names[item.kind]} · ${item.start}–${item.end}（结束地址不含） · ${item.kib} KiB`}>
          <div tabIndex={0} aria-label={`${names[item.kind]} ${item.start}–${item.end} ${item.kib} KiB`}
            style={{ width: `${(Number(item.end) - Number(item.start)) / map.length * 100}%`, background: colors[item.kind] }} />
        </Tooltip>)}
      </div>
      {map ? <Flex justify="space-between"><Text code>{map.start}</Text><Text code>{hexAddress(Number(map.start) + map.length)}</Text></Flex> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="扫描后显示内存分布" />}
    </Card>
    <Card title="音效当前占用位置">
      {live.length ? <Space orientation="vertical">{live.map(region => <Text key={region.index}>#{region.index} → <Text code>{hexAddress(region.start)}</Text>（{((region.end - region.start) / BLOCK).toLocaleString()} KiB）</Text>)}</Space>
        : <Text type="secondary">当前音效表没有指向暂存区的条目。</Text>}
    </Card>
    <Card title="扫描区段" extra={<Text type="secondary">扫描缓存与本地写入标记；上方地图叠加声表当前占用</Text>}>
      <Table id="memoryRuns" rowKey="start" columns={columns} dataSource={map?.runs || []} size="small"
        pagination={{ pageSize: 20, showSizeChanger: false }} scroll={{ x: 650 }} locale={{ emptyText: '请先扫描内存' }} />
    </Card>
  </Space>;
}
