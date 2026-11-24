const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { app, BrowserWindow, ipcMain, dialog, nativeTheme, shell } = require('electron');
const { Runtime } = require('./runtime');

const LOG = path.join(os.tmpdir(), 'lumixtool_startup.log');
function logLine(message) {
  try { fs.appendFileSync(LOG, `${new Date().toISOString()} ${message}\n`); } catch {}
}
logLine('--- LumixTool boot ---');
process.on('uncaughtException', error => logLine(`uncaught: ${error.stack || error}`));
process.on('unhandledRejection', error => logLine(`rejection: ${error?.stack || error}`));
if (!app || typeof app.whenReady !== 'function') {
  logLine('FATAL: Electron API missing; clear ELECTRON_RUN_AS_NODE.');
  process.exit(1);
}

app.setName('LumixTool');
const userData = path.join(app.getPath('appData'), 'LumixTool');
fs.mkdirSync(userData, { recursive: true });
app.setPath('userData', userData);
let win = null;
let operation = null;
const runtime = new Runtime({
  configPath: path.join(app.getPath('userData'), 'config.json'),
  legacyConfigPath: path.join(app.getPath('appData'), 's5-focus-sound', 'config.json'),
  // Packaged builds unpack python/ from the asar so an external interpreter can read it.
  scriptPath: path.join(__dirname.replace(/app\.asar$/, 'app.asar.unpacked'), 'python', 's5focus.py'),
  // Release builds ship the official Windows embeddable Python under resources/python.
  bundledPython: app.isPackaged && process.platform === 'win32' ? path.join(process.resourcesPath, 'python', 'python.exe') : null,
  mock: process.env.LUMIXTOOL_MOCK === '1',
  onProgress: progress => {
    if (win && !win.isDestroyed()) win.webContents.send('progress', progress);
  },
});

function createWindow() {
  win = new BrowserWindow({
    width: 1220, height: 850, minWidth: 960, minHeight: 700,
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#141414' : '#f5f5f5', title: 'LumixTool',
    autoHideMenuBar: true, show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true,
    },
  });
  win.setMenuBarVisibility(false);
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', event => event.preventDefault());
  win.webContents.on('will-attach-webview', event => event.preventDefault());
  win.webContents.on('before-input-event', (event, input) => {
    if (operation && (input.key === 'F5' || ((input.control || input.meta) && input.key.toLowerCase() === 'r'))) event.preventDefault();
  });
  win.webContents.on('did-fail-load', (_event, code, description) => logLine(`PAGE LOAD FAILED ${code} ${description}`));
  // Electron 45 uses the console-message event's details object.
  win.webContents.on('console-message', event => logLine(`RENDERER: ${event.level} ${event.message}`));
  win.webContents.on('render-process-gone', (_event, details) => {
    logLine(`RENDERER EXIT: ${details.reason} (exitCode ${details.exitCode}) appDir=${path.dirname(process.execPath)}`);
    if (details.reason !== 'launch-failed') return;
    // Chromium's sandboxed renderer runs with a restricted token that can only
    // read files the Users/Everyone groups may read. Folders whose ACL grants
    // only the owner (seen on a custom-ACL data drive) make it fail to start,
    // and the app would otherwise exit without ever showing a window.
    const appDir = path.dirname(process.execPath);
    dialog.showMessageBoxSync({
      type: 'error', title: 'LumixTool 无法启动',
      message: 'LumixTool 的界面进程无法读取程序文件，窗口打不开。',
      detail: `程序所在文件夹：\n${appDir}\n\n这个文件夹的权限只允许你的账户访问，Windows 的界面沙箱进程读不到其中的文件。\n\n解决办法（任选其一）：\n1. 把整个 LumixTool 文件夹移到桌面或「文档」等系统默认目录再运行；\n2. 在 cmd 中给 Users 组读取权限：\n   icacls "${appDir}" /grant *S-1-5-32-545:(OI)(CI)RX /T`,
      buttons: ['退出'],
    });
    app.quit();
  });
  win.once('ready-to-show', () => win?.show());
  win.webContents.once('did-finish-load', () => logLine('PAGE LOADED'));
  win.on('close', event => {
    if (!operation || operation === 'status' || operation === 'driver-status') return;
    const answer = dialog.showMessageBoxSync(win, {
      type: 'warning', title: '操作尚未完成',
      message: '设备操作正在进行，确定退出 LumixTool？',
      detail: '建议等待完成。退出会中断相机操作；已启动的管理员驱动脚本可能继续运行。',
      buttons: ['继续等待', '退出'], defaultId: 0, cancelId: 0,
    });
    if (answer === 0) event.preventDefault();
  });
  win.on('closed', () => { win = null; });
  if (process.env.LUMIXTOOL_DEV_URL) win.loadURL(process.env.LUMIXTOOL_DEV_URL);
  else win.loadFile(path.join(__dirname, 'renderer-dist', 'index.html'));
}

nativeTheme.on('updated', () => {
  if (win && !win.isDestroyed()) win.setBackgroundColor(nativeTheme.shouldUseDarkColors ? '#141414' : '#f5f5f5');
});

// Serialize device access even if more than one renderer request arrives.
async function deviceOperation(name, callback) {
  if (operation) return { ok: false, busy: true, error: '另一个操作正在进行，请等待完成。' };
  operation = name;
  try { return await callback(); }
  catch (error) { return { ok: false, connected: false, error: error.message || String(error) }; }
  finally { operation = null; }
}

ipcMain.handle('env', () => runtime.environment());
ipcMain.handle('pick-python', async () => {
  if (operation) return { ok: false, error: '请等待相机操作完成后再更换 Python。' };
  const result = await dialog.showOpenDialog(win, {
    title: '为 LumixTool 选择 Python 3', properties: ['openFile'],
    filters: process.platform === 'win32' ? [{ name: 'Python', extensions: ['exe'] }] : [],
  });
  if (result.canceled || !result.filePaths[0]) return null;
  return runtime.setPython(result.filePaths[0]);
});
ipcMain.handle('pick-audio', async () => {
  if (operation && operation !== 'status') return null;
  const result = await dialog.showOpenDialog(win, {
    title: '选择替换音效', properties: ['openFile'],
    filters: [{ name: '音频', extensions: ['wav', 'mp3', 'm4a', 'aac', 'flac', 'ogg', 'opus'] }],
  });
  return result.canceled ? null : result.filePaths[0] || null;
});
ipcMain.handle('read-file', async (_event, filename) => {
  if (typeof filename !== 'string' || !path.isAbsolute(filename)) throw new Error('无效的文件路径。');
  const stat = await fs.promises.stat(filename);
  if (!stat.isFile() || stat.size > 100 * 1024 * 1024) throw new Error('请选择不超过 100 MB 的音频文件。');
  return fs.promises.readFile(filename);
});
ipcMain.handle('status', () => deviceOperation('status', () => runtime.inspect()));
ipcMain.handle('driver-status', () => deviceOperation('driver-status', () => runtime.driverStatus()));
ipcMain.handle('driver-install', () => deviceOperation('driver-install', () => runtime.installDriver()));
ipcMain.handle('driver-uninstall', (_event, options) => deviceOperation('driver-uninstall', () => runtime.uninstallDriver({ removeCertificate: options?.removeCertificate === true })));
ipcMain.handle('open-external', async (_event, url) => {
  if (url !== 'https://zadig.akeo.ie/') return { ok: false, error: '不允许打开此链接。' };
  try { await shell.openExternal(url); return { ok: true }; }
  catch (error) { return { ok: false, error: error.message }; }
});
ipcMain.handle('dump', () => deviceOperation('dump', () => runtime.inspect()));
ipcMain.handle('scan-memory', () => deviceOperation('scan-memory', () => runtime.scanMemory()));
ipcMain.handle('memory-map', (_event, version) => runtime.memoryMap(version));
ipcMain.handle('export-memory', (_event, version) => deviceOperation('export-memory', async () => {
  const cached = runtime.memoryMap(version);
  if (!cached.ok || !cached.map) return { ok: false, error: cached.error || '请先扫描内存。' };
  const result = await dialog.showSaveDialog(win, {
    title: '导出内存扫描 JSON', defaultPath: `LumixTool-memory-${cached.map.bodyVersion}.json`,
    filters: [{ name: 'JSON', extensions: ['json'] }],
  });
  if (result.canceled || !result.filePath) return { ok: true, canceled: true };
  await fs.promises.writeFile(result.filePath, JSON.stringify(cached.map, null, 2), 'utf8');
  return { ok: true };
}));
ipcMain.handle('apply-slot', (_event, payload) => deviceOperation('apply-slot', () => runtime.soundBatch('apply', { ...payload, indices: [payload?.index] })));
ipcMain.handle('apply-slots', (_event, payload) => deviceOperation('apply-slots', () => runtime.soundBatch('apply', payload)));
ipcMain.handle('restore-id', (_event, payload) => deviceOperation('restore-id', () => runtime.soundBatch('restore', { ...payload, indices: [payload?.index] })));
ipcMain.handle('restore-all', (_event, payload) => deviceOperation('restore-all', () => runtime.soundBatch('restore', { version: payload?.version })));
ipcMain.handle('rename-sound', (_event, payload) => deviceOperation('rename-sound', () => runtime.renameSound(payload)));
ipcMain.handle('apply', (_event, payload) => deviceOperation('apply', () => runtime.apply(payload)));
ipcMain.handle('restore', () => deviceOperation('restore', () => runtime.restore()));
ipcMain.handle('mock-configure', (_event, options) => {
  if (operation) return { ok: false, error: '请等待当前操作完成。' };
  return runtime.configureMock(options);
});

app.whenReady().then(() => {
  logLine('app ready');
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
}).catch(error => logLine(`whenReady failed: ${error.stack || error}`));
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
