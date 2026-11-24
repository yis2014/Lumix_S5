const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

test('the real guide renders stable driver controls, platform restrictions and operation results', async () => {
  const { createServer } = await import('vite');
  const server = await createServer({ root: path.resolve(__dirname, '..') });
  try {
    const { default: Guide } = await server.ssrLoadModule('/src/components/ConnectionGuide.jsx');
    const { DriverStatus, DriverResult } = await server.ssrLoadModule('/src/components/DriverSetup.jsx');
    const driver = { supported: true, present: true, ok: false };
    const device = { driver, device: {}, api: {}, refreshDriver() {} };
    const html = renderToStaticMarkup(React.createElement(Guide, { device, navigate() {}, active: true }));
    for (const id of ['driverStatus', 'installDriver', 'recheckDriver']) assert.ok(html.includes(`id="${id}"`));
    assert.ok(html.includes('已连接但未安装驱动'));
    assert.ok(html.includes('需要管理员权限'));
    assert.ok(html.includes('本机自签名证书'));
    assert.ok(html.includes('高级'));
    const unsupported = renderToStaticMarkup(React.createElement(Guide, { device: { ...device, driver: { supported: false } }, navigate() {} }));
    assert.ok(unsupported.includes('驱动安装仅支持 Windows 10/11'));
    assert.match(unsupported, /<button[^>]*id="installDriver"[^>]*disabled/);
    assert.match(unsupported, /<button[^>]*id="recheckDriver"[^>]*disabled/);
    const working = renderToStaticMarkup(React.createElement(Guide, { device: { ...device, locked: true, busy: { tool: 'driver', label: '正在安装驱动' } }, navigate() {} }));
    assert.ok(working.includes('等待管理员授权与驱动操作完成'));
    const good = renderToStaticMarkup(React.createElement(DriverStatus, { driver: { ...driver, ok: true } }));
    assert.ok(good.includes('驱动正常'));
    const result = values => renderToStaticMarkup(React.createElement(DriverResult, { device: { ...device, driverResult: values } }));
    assert.ok(result({ ok: false, cancelled: true }).includes('已取消管理员授权，可重试'));
    assert.ok(result({ ok: false, message: 'bad signature' }).includes('驱动操作失败'));
    assert.ok(result({ ok: true, action: 'install' }).includes('驱动包已添加，请确认设备绑定'));
    assert.ok(result({ ok: true, action: 'uninstall' }).includes('LumixTool 驱动包已卸载'));
  } finally { await server.close(); }
});
