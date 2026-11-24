const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { execFile } = require('node:child_process');

const INTERFACE_GUID = '{CDE53111-593A-43C9-AB10-EA9DACF2C573}';
const DRIVER_SCENARIOS = ['ok', 'absent', 'normal', 'missing', 'wrong-driver', 'missing-guid', 'unknown-guid'];
const DRIVER_RESULTS = ['success', 'failure', 'cancelled'];
const serviceId = /^USB\\VID_04DA&PID_2370(?:&MI_00)?\\[^\\\s]+$/i;
const normalId = /^USB\\VID_04DA&PID_2382(?:&[^\\\s]+)?\\[^\\\s]+$/i;
const psQuote = value => `'${value.replaceAll("'", "''")}'`;
const encodePowerShell = value => Buffer.from(value, 'utf16le').toString('base64');

function decodeOutput(buffer) {
  if (!Buffer.isBuffer(buffer)) return String(buffer || '');
  const utf16 = buffer[0] === 0xff && buffer[1] === 0xfe || buffer[1] === 0 && buffer[3] === 0;
  return buffer.toString(utf16 ? 'utf16le' : 'utf8').replace(/^\uFEFF/, '');
}

function runCommand(executable, args, { timeout = 25000 } = {}) {
  return new Promise((resolve, reject) => {
    execFile(executable, args, { windowsHide: true, encoding: 'buffer', maxBuffer: 2 * 1024 * 1024, timeout }, (error, stdout, stderr) => {
      if (error && typeof error.code !== 'number') return reject(error);
      resolve({ code: error?.code || 0, stdout: decodeOutput(stdout), stderr: decodeOutput(stderr) });
    });
  });
}

function summarizeDevices(devices, source) {
  const service = devices.filter(device => serviceId.test(device.instanceId));
  // A composite parent bound to usbccgp is not the service interface. Prefer MI_00.
  const candidates = service.some(device => /&MI_00\\/i.test(device.instanceId))
    ? service.filter(device => /&MI_00\\/i.test(device.instanceId)) : service;
  const inspected = candidates.map(device => {
    const winusb = /^winusb$/i.test(device.service || '');
    const guidRegistered = device.guidDetectable === true
      ? device.guids.some(guid => guid.toUpperCase() === INTERFACE_GUID) : null;
    const healthy = device.problemCode === 0;
    return { ...device, winusb, guidRegistered, ok: winusb && healthy && guidRegistered === true };
  });
  const best = inspected.find(device => device.ok) || inspected.find(device => device.winusb) || inspected[0];
  return {
    supported: true, present: service.length > 0, normalPresent: devices.some(device => normalId.test(device.instanceId)),
    driver: best?.service || best?.provider || null, provider: best?.provider || null,
    driverDetectable: best?.serviceDetectable ?? false,
    ok: best?.ok || false, winusb: best?.winusb || false, guidRegistered: best?.guidRegistered ?? null,
    problemCode: best?.problemCode ?? null, source, devices: inspected,
  };
}

function parsePnpJson(text) {
  const value = JSON.parse(text.replace(/^\uFEFF/, '').trim());
  const rows = value === null ? [] : Array.isArray(value) ? value : [value];
  if (rows.some(row => !row || typeof row !== 'object' || typeof row.instanceId !== 'string')) {
    throw new Error('Invalid PnP JSON device list.');
  }
  return summarizeDevices(rows.map(row => ({
    instanceId: row.instanceId, service: typeof row.service === 'string' ? row.service : null,
    serviceDetectable: row.serviceDetectable === true || typeof row.service === 'string' || row.problemCode === 28,
    provider: typeof row.provider === 'string' ? row.provider : null,
    problemCode: Number.isInteger(row.problemCode) ? row.problemCode : null,
    guidDetectable: row.guidDetectable === true,
    guids: (Array.isArray(row.guids) ? row.guids : [row.guids]).filter(guid => typeof guid === 'string'),
  })), 'powershell');
}

function parsePnputil(text) {
  const devices = [];
  // Do not depend on translated labels, names, status words, or provider strings.
  for (const block of text.split(/\r?\n[\t ]*\r?\n/)) {
    const instanceIds = [...block.matchAll(/USB\\VID_04DA&PID_(?:2370|2382)(?:&[^\\\s:：]+)?\\[^\s:：]+/gi)].map(match => match[0]);
    for (const instanceId of new Set(instanceIds)) {
      const winusb = /[:：]\s*WinUSB\s*$/im.test(block);
      devices.push({ instanceId, service: winusb ? 'WinUSB' : null, serviceDetectable: winusb,
        provider: null, problemCode: null, guids: [], guidDetectable: false });
    }
  }
  return summarizeDevices(devices, 'pnputil');
}

class DriverManager {
  constructor({ platform = process.platform, directory = path.join(__dirname, 'driver'), run = runCommand, mock = false, mockState = {} } = {}) {
    Object.assign(this, { platform, directory, run, mock, mockState });
    const system = process.env.SystemRoot || 'C:\\Windows';
    const systemDirectory = process.arch === 'ia32' && process.env.PROCESSOR_ARCHITEW6432 ? 'Sysnative' : 'System32';
    this.powershell = path.win32.join(system, systemDirectory, 'WindowsPowerShell', 'v1.0', 'powershell.exe');
    this.pnputil = path.win32.join(system, systemDirectory, 'pnputil.exe');
  }

  async status() {
    if (this.mock) return this.mockStatus();
    if (this.platform !== 'win32') return { supported: false };
    let primaryError;
    try {
      // fs can read inside app.asar; PowerShell cannot. Pass this read-only script encoded.
      const script = await fs.readFile(path.join(this.directory, 'driver-status.ps1'), 'utf8');
      const result = await this.run(this.powershell, ['-NoProfile', '-NonInteractive', '-EncodedCommand', encodePowerShell(script)]);
      if (result.code !== 0) throw new Error(result.stderr || result.stdout || `PowerShell exit ${result.code}`);
      return parsePnpJson(result.stdout);
    } catch (error) { primaryError = error.message; }
    try {
      const result = await this.run(this.pnputil, ['/enum-devices', '/connected', '/ids']);
      if (result.code !== 0 || !result.stdout.trim()) throw new Error(result.stderr || result.stdout || `pnputil exit ${result.code}`);
      return { ...parsePnputil(result.stdout), warning: `无法读取完整驱动属性，GUID 状态未知。${primaryError}` };
    } catch (error) {
      return { supported: true, present: null, normalPresent: null, driver: null, ok: false,
        error: `驱动检测失败：${primaryError}\n${error.message}` };
    }
  }

  async change(action, { removeCertificate = false } = {}) {
    if (!['install', 'uninstall'].includes(action)) throw new Error('Invalid driver action.');
    if (this.mock) return this.mockChange(action);
    if (this.platform !== 'win32') return { supported: false, ok: false, message: '驱动安装仅支持 Windows 10/11。' };
    let work;
    try {
      work = await fs.mkdtemp(path.join(os.tmpdir(), 'LumixTool-elevation-'));
      // Copy resources out of app.asar before elevation; also works in development.
      for (const name of ['lumixtool_winusb.inf', `${action}-driver.ps1`]) {
        await fs.copyFile(path.join(this.directory, name), path.join(work, name));
      }
      const resultPath = path.join(work, 'result.json');
      const scriptPath = path.join(work, `${action}-driver.ps1`);
      const inner = `& ${psQuote(scriptPath)} -ResultPath ${psQuote(resultPath)}${action === 'uninstall' && removeCertificate === true ? ' -RemoveCertificate' : ''}`;
      const wrapper = `$ErrorActionPreference = 'Stop'
try {
  $child = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -Verb RunAs -Wait -PassThru -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', '${encodePowerShell(inner)}')
  exit $child.ExitCode
} catch {
  $failure = $_.Exception
  while ($failure) {
    if ($failure.NativeErrorCode -eq 1223) { exit 1223 }
    $failure = $failure.InnerException
  }
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}`;
      const launch = await this.run(this.powershell, ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', encodePowerShell(wrapper)], { timeout: 0 });
      let raw;
      try { raw = await fs.readFile(resultPath, 'utf8'); }
      catch (error) {
        if (error.code !== 'ENOENT') throw error;
        const cancelled = launch.code === 1223 || launch.code === 0;
        return { ok: false, cancelled, step: 'elevation', pnputilExit: null, output: launch.stderr || launch.stdout,
          message: cancelled ? '管理员授权已取消，未收到安装脚本结果。' : '无法启动管理员脚本，未收到结果。' };
      }
      const result = JSON.parse(raw.replace(/^\uFEFF/, ''));
      if (!result || typeof result.ok !== 'boolean' || typeof result.step !== 'string' || typeof result.message !== 'string' ||
          typeof result.output !== 'string' || !(result.pnputilExit === null || Number.isInteger(result.pnputilExit))) {
        throw new Error('管理员脚本返回了无效的结果。');
      }
      return { ok: result.ok, step: result.step, message: result.message, pnputilExit: result.pnputilExit, output: result.output };
    } catch (error) {
      return { ok: false, step: 'launch', message: error.message, pnputilExit: null, output: '' };
    } finally {
      if (work) await fs.rm(work, { recursive: true, force: true }).catch(() => {});
    }
  }

  mockStatus() {
    const state = this.mockState;
    const scenario = state.scenario === 'disconnected' ? 'absent' : state.driverScenario;
    const present = !['absent', 'normal'].includes(scenario);
    const winusb = ['ok', 'missing-guid', 'unknown-guid'].includes(scenario);
    return { supported: true, mock: true, present, normalPresent: scenario === 'normal',
      driver: winusb ? 'WinUSB' : scenario === 'wrong-driver' ? 'libusbK' : null,
      provider: winusb ? 'LumixTool' : null, driverDetectable: present, winusb, ok: scenario === 'ok',
      guidRegistered: scenario === 'unknown-guid' || !present ? null : scenario === 'ok',
      problemCode: scenario === 'missing' ? 28 : 0, source: 'mock' };
  }

  async mockChange(action) {
    await new Promise(resolve => setTimeout(resolve, 500));
    const outcome = this.mockState.driverResult;
    if (outcome === 'cancelled') return { ok: false, cancelled: true, step: 'elevation', message: '模拟：管理员授权已取消。', pnputilExit: null, output: '' };
    if (outcome === 'failure') return { ok: false, step: 'pnputil', message: '模拟：Windows 拒绝驱动包。', pnputilExit: 5, output: 'Mock pnputil: access denied.' };
    if (this.mockStatus().present) this.mockState.driverScenario = action === 'install' ? 'ok' : 'missing';
    return { ok: true, step: 'complete', message: action === 'install' ? '模拟：驱动包已安装。' : '模拟：驱动已卸载。', pnputilExit: 0, output: 'Mock pnputil: success.' };
  }
}

module.exports = { DriverManager, parsePnpJson, parsePnputil, INTERFACE_GUID, DRIVER_SCENARIOS, DRIVER_RESULTS, decodeOutput };
