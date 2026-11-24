const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const { EventEmitter } = require('node:events');

async function launch({ dark = false, devUrl, saveResult = { canceled: true } } = {}) {
  const handlers = new Map();
  const windows = [];
  const calls = [];
  const app = new EventEmitter();
  const paths = { appData: '/local/app-data', userData: '/local/old' };
  Object.assign(app, {
    setName: name => { app.name = name; },
    getPath: key => paths[key], setPath: (key, value) => { paths[key] = value; },
    whenReady: () => Promise.resolve(), quit() {},
  });
  class BrowserWindow extends EventEmitter {
    constructor(options) {
      super(); this.options = options;
      this.webContents = new EventEmitter();
      this.webContents.setWindowOpenHandler = handler => { this.openHandler = handler; };
      this.webContents.send = (...args) => calls.push(args);
      windows.push(this);
    }
    static getAllWindows() { return windows; }
    setMenuBarVisibility() {}
    loadFile(filename) { this.filename = filename; }
    loadURL(url) { this.url = url; }
    setBackgroundColor(color) { this.backgroundColor = color; }
    isDestroyed() { return false; }
    show() {}
  }
  let runtime;
  class Runtime {
    constructor(options) { this.options = options; runtime = this; }
    async environment() { return { mock: false }; }
    async status() { return { connected: false }; }
    async inspect() { return this.status(); }
    async apply(payload) { calls.push(payload); return { ok: true }; }
    async restore() { return { ok: true }; }
    async driverStatus() { return { supported: false }; }
    async installDriver() { return { ok: true, message: 'installed' }; }
    async uninstallDriver(options) { calls.push(options); return { ok: true, message: 'uninstalled' }; }
    configureMock() { return { ok: false }; }
  }
  const ipcMain = { handle: (name, callback) => handlers.set(name, callback) };
  const fakeProcess = new EventEmitter();
  Object.assign(fakeProcess, { env: { LUMIXTOOL_DEV_URL: devUrl }, platform: 'darwin', exit: () => { throw new Error('unexpected exit'); } });
  const nativeTheme = new EventEmitter();
  nativeTheme.shouldUseDarkColors = dark;
  const electron = { app, BrowserWindow, ipcMain, nativeTheme, shell: { openExternal: async url => { calls.push(url); } }, dialog: {
    showMessageBoxSync: () => 0,
    showSaveDialog: async (_window, options) => { calls.push({ saveDialog: options }); return saveResult; },
  } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../main.js'), 'utf8'), {
    __dirname: path.resolve(__dirname, '..'), process: fakeProcess,
    require: name => name === 'electron' ? electron : name === './runtime' ? { Runtime }
      : name === 'node:fs' ? { ...fs, appendFileSync() {}, mkdirSync() {}, promises: {
        ...fs.promises, writeFile: async (filename, data) => { calls.push({ filename, data }); },
      } } : require(name),
  });
  await Promise.resolve();
  return { handlers, windows, calls, runtime, app, paths, nativeTheme };
}

test('main loads the built React renderer with sandboxed preload and no tool discovery IPC', async () => {
  const { windows: [window], runtime, app, paths, handlers } = await launch();
  assert.equal(app.name, 'LumixTool');
  assert.equal(paths.userData, path.normalize('/local/app-data/LumixTool'));
  assert.equal(runtime.options.legacyConfigPath, path.normalize('/local/app-data/s5-focus-sound/config.json'));
  assert.equal(window.options.title, 'LumixTool');
  assert.equal(window.options.webPreferences.contextIsolation, true);
  assert.equal(window.options.webPreferences.nodeIntegration, false);
  assert.equal(window.options.webPreferences.sandbox, true);
  assert.equal(window.openHandler().action, 'deny');
  let navigationPrevented = false;
  window.webContents.emit('will-navigate', { preventDefault() { navigationPrevented = true; } });
  assert.equal(navigationPrevented, true);
  assert.equal(window.filename, path.resolve(__dirname, '../renderer-dist/index.html'));
  assert.equal(window.options.backgroundColor, '#f5f5f5');
  assert.equal(handlers.has('list-tools'), false);
});

test('main uses the dev URL when provided and follows native theme changes', async () => {
  const { windows: [window], nativeTheme } = await launch({ dark: true, devUrl: 'http://127.0.0.1:5173' });
  assert.equal(window.url, 'http://127.0.0.1:5173');
  assert.equal(window.filename, undefined);
  assert.equal(window.options.backgroundColor, '#141414');
  nativeTheme.shouldUseDarkColors = false;
  nativeTheme.emit('updated');
  assert.equal(window.backgroundColor, '#f5f5f5');
});

test('main serializes apply, restore and status; forwards PCM payload unchanged; keeps progress IPC', async () => {
  const { handlers, runtime, windows: [window], calls } = await launch();
  let complete;
  runtime.apply = payload => {
    calls.push(payload);
    return new Promise(resolve => { complete = resolve; });
  };
  const payload = { pcm: new ArrayBuffer(88200), samples: 44100 };
  const pending = handlers.get('apply')({}, payload);
  assert.equal((await handlers.get('restore')()).busy, true);
  assert.equal((await handlers.get('status')()).busy, true);
  assert.equal(calls[0], payload);
  runtime.options.onProgress({ done: 2000, total: 44100 });
  assert.equal(calls[1][0], 'progress');
  assert.deepEqual(calls[1][1], { done: 2000, total: 44100 });
  let closePrevented = false;
  window.emit('close', { preventDefault() { closePrevented = true; } });
  assert.equal(closePrevented, true);
  let reloadPrevented = false;
  window.webContents.emit('before-input-event', { preventDefault() { reloadPrevented = true; } }, { key: 'r', meta: true });
  assert.equal(reloadPrevented, true);
  complete({ ok: true });
  assert.equal((await pending).ok, true);
  assert.equal((await handlers.get('restore')()).ok, true);
  runtime.apply = async () => { throw new Error('backend error text'); };
  assert.equal((await handlers.get('apply')({}, payload)).error, 'backend error text');
  assert.equal((await handlers.get('status')()).connected, false);
});

test('renderer CSP allows Ant Design styles and local audio, with no inline scripts or remote resources', () => {
  const html = fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8');
  assert.ok(html.includes("script-src 'self';"));
  assert.ok(html.includes("style-src 'self' 'unsafe-inline';"));
  assert.ok(html.includes("img-src 'self' data: blob:;"));
  assert.ok(html.includes("media-src 'self' blob: data:;"));
  assert.ok(html.includes("connect-src 'self';"));
  assert.ok(!html.includes('https://'));
  for (const match of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) {
    assert.ok(match[1].includes('src='));
    assert.equal(match[2].trim(), '');
    const source = /src="([^"]+)"/.exec(match[1])[1];
    assert.ok(fs.existsSync(path.join(__dirname, '..', source)), `missing local resource: ${source}`);
  }
});

test('sound batch IPC holds the device lock through the entire batch and exposes explicit channels', async () => {
  const { handlers, runtime } = await launch();
  let finish;
  let received;
  runtime.soundBatch = (kind, payload) => {
    received = { kind, payload };
    return new Promise(resolve => { finish = resolve; });
  };
  const payload = { indices: [1, 20, 21], pcm: new ArrayBuffer(2), samples: 1 };
  const pending = handlers.get('apply-slots')({}, payload);
  assert.equal(received.kind, 'apply');
  assert.equal(received.payload, payload);
  for (const channel of ['status', 'dump', 'restore-all', 'restore-id', 'apply-slot', 'rename-sound']) {
    assert.equal((await handlers.get(channel)({}, { index: 1 })).busy, true, channel);
  }
  finish({ ok: false, failedIndex: 20, succeeded: [1] });
  const result = await pending;
  assert.equal(result.failedIndex, 20);
  assert.deepEqual(result.succeeded, [1]);
  assert.equal((await handlers.get('status')()).connected, false);
});

test('driver IPC shares the camera lock in both directions and sanitizes uninstall options', async () => {
  const { handlers, runtime, calls } = await launch();
  assert.equal((await handlers.get('driver-status')()).supported, false);
  for (const driverChannel of ['driver-status', 'driver-install', 'driver-uninstall']) {
    let finish;
    runtime[driverChannel === 'driver-status' ? 'driverStatus' : driverChannel === 'driver-install' ? 'installDriver' : 'uninstallDriver'] = () => new Promise(resolve => { finish = resolve; });
    const pending = handlers.get(driverChannel)({}, { removeCertificate: true });
    for (const channel of ['status', 'apply', 'restore', 'dump', 'apply-slots', 'driver-install', 'driver-uninstall', 'driver-status']) {
      assert.equal((await handlers.get(channel)({}, {})).busy, true, `${driverChannel} locks ${channel}`);
    }
    assert.equal(handlers.get('mock-configure')({}, {}).ok, false);
    finish({ ok: true });
    assert.equal((await pending).ok, true);
  }
  let finishApply;
  runtime.apply = () => new Promise(resolve => { finishApply = resolve; });
  const camera = handlers.get('apply')({}, {});
  assert.equal((await handlers.get('driver-install')()).busy, true);
  finishApply({ ok: true });
  await camera;
  runtime.uninstallDriver = async options => { calls.push(options); return { ok: true }; };
  await handlers.get('driver-uninstall')({}, { removeCertificate: 'yes', scriptPath: 'untrusted.ps1' });
  assert.equal(calls.at(-1).removeCertificate, false);
  assert.deepEqual(Object.keys(calls.at(-1)), ['removeCertificate']);
  await handlers.get('driver-uninstall')({}, { removeCertificate: true });
  assert.equal(calls.at(-1).removeCertificate, true);
});

test('external links use an exact main-process allowlist', async () => {
  const { handlers, calls } = await launch();
  for (const url of ['http://zadig.akeo.ie/', 'https://zadig.akeo.ie', 'https://zadig.akeo.ie/evil', 'https://zadig.akeo.ie.evil/', 'file:///tmp/evil', null]) {
    assert.equal((await handlers.get('open-external')({}, url)).ok, false);
  }
  assert.equal(calls.length, 0);
  assert.equal((await handlers.get('open-external')({}, 'https://zadig.akeo.ie/')).ok, true);
  assert.deepEqual(calls, ['https://zadig.akeo.ie/']);
});

test('preload exposes explicit driver methods and fixes the Zadig URL', () => {
  let api;
  const calls = [];
  const electron = {
    contextBridge: { exposeInMainWorld: (_key, value) => { api = value; } },
    ipcRenderer: { invoke: (...args) => { calls.push(args); } }, webUtils: {},
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../preload.js'), 'utf8'), { require: () => electron });
  api.driverStatus(); api.installDriver(); api.uninstallDriver({ removeCertificate: true }); api.openZadig('https://evil.example/');
  assert.equal(calls[0][0], 'driver-status');
  assert.equal(calls[1][0], 'driver-install');
  assert.equal(calls[2][0], 'driver-uninstall');
  assert.equal(calls[2][1].removeCertificate, true);
  assert.deepEqual(calls[3], ['open-external', 'https://zadig.akeo.ie/']);
});

test('Vite development HTML keeps refresh scripts external and only adds the local WebSocket origin', async () => {
  const { createServer } = await import('vite');
  const server = await createServer({ root: path.resolve(__dirname, '..') });
  try {
    const html = await server.transformIndexHtml('/', fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8'));
    assert.ok(html.includes("script-src 'self';"));
    assert.ok(html.includes("connect-src 'self' ws://127.0.0.1:5173;"));
    assert.ok(html.includes('src="/@lumix-refresh"'));
    for (const match of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) {
      assert.ok(match[1].includes('src='), 'development must not inject an inline script');
      assert.equal(match[2].trim(), '');
    }
    let refreshHandler;
    server.config.plugins.find(plugin => plugin.name === 'development-csp').configureServer({
      middlewares: { use: (_route, handler) => { refreshHandler = handler; } },
    });
    let script;
    refreshHandler({}, { setHeader() {}, end(value) { script = value; } });
    assert.ok(script.includes('from "/@react-refresh"'));
    assert.ok(!script.includes('__BASE__'));
  } finally { await server.close(); }
});

test('memory scan holds the shared device lock and forwards scan progress', async () => {
  const { handlers, runtime, calls } = await launch();
  let finish;
  runtime.scanMemory = () => new Promise(resolve => { finish = resolve; });
  runtime.memoryMap = version => ({ ok: true, map: { bodyVersion: version } });
  const pending = handlers.get('scan-memory')();
  for (const channel of ['status', 'dump', 'apply-slots', 'restore-id', 'driver-install', 'scan-memory']) {
    assert.equal((await handlers.get(channel)({}, {})).busy, true, channel);
  }
  runtime.options.onProgress({ phase: 'scan', done: 1024, total: 8192 });
  assert.equal(calls.at(-1)[1].phase, 'scan');
  assert.equal(handlers.get('memory-map')({}, '0x0290').map.bodyVersion, '0x0290');
  finish({ ok: true });
  assert.equal((await pending).ok, true);
  assert.equal((await handlers.get('status')()).connected, false);
});

test('memory export saves the main-process cached map through a native dialog', async () => {
  const { handlers, runtime, calls } = await launch({ saveResult: { canceled: false, filePath: '/tmp/map.json' } });
  const map = { bodyVersion: '0x0290', scannedAt: 'now', start: '0x8F000000', length: 1024, runs: [] };
  runtime.memoryMap = version => ({ ok: true, map: version === '0x0290' ? map : null });
  assert.equal((await handlers.get('export-memory')({}, '0x0208')).ok, false);
  assert.equal(calls.length, 0);
  assert.equal((await handlers.get('export-memory')({}, '0x0290')).ok, true);
  assert.equal(calls[0].saveDialog.defaultPath, 'LumixTool-memory-0x0290.json');
  assert.equal(calls[1].filename, '/tmp/map.json');
  assert.deepEqual(JSON.parse(calls[1].data), map);
  const canceled = await launch();
  canceled.runtime.memoryMap = () => ({ ok: true, map });
  assert.equal((await canceled.handlers.get('export-memory')({}, '0x0290')).canceled, true);
  assert.equal(canceled.calls.length, 1);
});

test('preload exposes only explicit memory scan/cache/export channels', () => {
  let api;
  const calls = [];
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../preload.js'), 'utf8'), { require: () => ({
    contextBridge: { exposeInMainWorld: (_key, value) => { api = value; } },
    ipcRenderer: { invoke: (...args) => { calls.push(args); } }, webUtils: {},
  }) });
  api.scanMemory(); api.memoryMap('0x0290'); api.exportMemory('0x0290');
  assert.deepEqual(calls, [['scan-memory'], ['memory-map', '0x0290'], ['export-memory', '0x0290']]);
});
