import { DatabaseOutlined, SoundOutlined } from '@ant-design/icons';
import Sounds from './sounds/Sounds';
import Memory from './memory/Memory';

export const tools = [
  {
    id: 'focus-sound',
    title: '音效替换',
    icon: <SoundOutlined />,
    description: '管理 28 项相机音效，逐项替换或批量定位触发动作。',
    scope: 'DC-S5 专属',
    component: Sounds,
  },
  {
    id: 'memory',
    title: '内存诊断',
    icon: <DatabaseOutlined />,
    description: '只读扫描相机 RAM 暂存区，查看哪些区域可安全写入',
    scope: '只读 · DC-S5',
    component: Memory,
  },
];
