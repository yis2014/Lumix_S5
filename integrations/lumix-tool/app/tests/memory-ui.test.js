const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const { mockMemoryMap } = require('../memory.mjs');

test('memory tool renders read-only controls, live ownership, run sizes and disabled states', async () => {
  const { createServer } = await import('vite');
  const server = await createServer({ root: path.resolve(__dirname, '..') });
  try {
    const { default: Memory } = await server.ssrLoadModule('/src/tools/memory/Memory.jsx');
    const map = { ...mockMemoryMap(), bodyVersion: '0x0290', scannedAt: '2026-11-22T00:00:00Z' };
    const device = { api: {}, ready: true, locked: false, device: { memoryMap: map,
      soundTable: { entries: [{ index: 1, addr: 0x0F000010, size: 88200 }] } } };
    const html = renderToStaticMarkup(React.createElement(Memory, { device }));
    for (const id of ['scanMemory', 'memoryMap', 'memoryRuns', 'exportMemory']) assert.ok(html.includes(`id="${id}"`), id);
    for (const text of ['只读诊断，不会写入相机', '0x0290', '0x8F000000', '87 KiB', '#1', '最大连续可写入', '其他数据', '全零']) assert.ok(html.includes(text), text);
    const disconnected = renderToStaticMarkup(React.createElement(Memory, { device: { ...device, ready: false, device: {} } }));
    assert.match(disconnected, /<button[^>]*id="scanMemory"[^>]*disabled/);
    assert.match(disconnected, /<button[^>]*id="exportMemory"[^>]*disabled/);
    const busy = renderToStaticMarkup(React.createElement(Memory, { device: { ...device, locked: true,
      busy: { tool: 'memory' }, progress: { phase: 'scan', done: 4096, total: 8192 } } }));
    assert.match(busy, /<button[^>]*id="scanMemory"[^>]*disabled/);
    assert.ok(busy.includes('正在只读扫描 RAM'));
    assert.ok(busy.includes('50%'));
  } finally { await server.close(); }
});
