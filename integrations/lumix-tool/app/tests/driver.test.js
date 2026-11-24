const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { DriverManager, parsePnpJson, parsePnputil, INTERFACE_GUID, decodeOutput } = require('../driver');

const instanceId = 'USB\\VID_04DA&PID_2370\\CAMERA';
const goodDevice = { instanceId, service: 'WinUSB', provider: 'LumixTool', problemCode: 0, guidDetectable: true, guids: [INTERFACE_GUID.toLowerCase()] };
const jsonStatus = rows => parsePnpJson(JSON.stringify(rows));

test('PnP JSON distinguishes binding, GUID absence, denied registry access and device problems', () => {
  const good = jsonStatus(goodDevice); // ConvertTo-Json can return a singleton or array.
  assert.equal(good.present, true);
  assert.equal(good.ok, true);
  assert.equal(good.driver, 'WinUSB');
  assert.equal(good.guidRegistered, true);
  assert.equal(jsonStatus([{ ...goodDevice, provider: 'Microsoft' }]).ok, true);
  assert.equal(jsonStatus([{ ...goodDevice, service: 'libusbK' }]).ok, false);
  assert.equal(jsonStatus([{ ...goodDevice, service: null, provider: null, problemCode: 28 }]).driver, null);
  const missing = jsonStatus([{ ...goodDevice, guids: [] }]);
  assert.equal(missing.ok, false);
  assert.equal(missing.guidRegistered, false);
  const denied = jsonStatus([{ ...goodDevice, guidDetectable: false, guids: null }]);
  assert.equal(denied.ok, false);
  assert.equal(denied.guidRegistered, null);
  assert.equal(jsonStatus([{ ...goodDevice, problemCode: 52 }]).ok, false);
  assert.equal(jsonStatus([{ ...goodDevice, problemCode: null }]).ok, false);
  assert.equal(jsonStatus([{ ...goodDevice, guids: 'wrong-guid' }]).ok, false);
  assert.equal(jsonStatus([{ ...goodDevice, guids: INTERFACE_GUID }]).ok, true);
  assert.equal(jsonStatus(null).present, false);
  assert.equal(jsonStatus([]).present, false);
  assert.throws(() => parsePnpJson('not JSON'));
  assert.throws(() => jsonStatus({ error: 'access denied' }));
  assert.throws(() => jsonStatus([null]));
});

test('composite interface 0 takes precedence over parent and interface 1; IDs must match exactly', () => {
  const composite = jsonStatus([
    { ...goodDevice, service: 'usbccgp', guids: [] },
    { ...goodDevice, instanceId: 'usb\\vid_04da&pid_2370&mi_00\\INTERFACE0' },
    { ...goodDevice, instanceId: 'USB\\VID_04DA&PID_2370&MI_01\\INTERFACE1', service: 'libusbK' },
    { instanceId: 'USB\\VID_04DA&PID_2382\\NORMAL' },
  ]);
  assert.equal(composite.ok, true);
  assert.equal(composite.devices.length, 1);
  assert.equal(composite.normalPresent, true);
  assert.equal(jsonStatus([{ ...goodDevice, instanceId: `${instanceId}EXTRA` }]).ok, true); // Any serial is valid.
  for (const id of ['USB\\VID_04DA&PID_23700\\X', 'USB\\VID_14DA&PID_2370\\X', 'USB\\VID_04DA&PID_2370&MI_01\\X', 'USB\\VID_04DA&PID_2370']) {
    assert.equal(jsonStatus([{ ...goodDevice, instanceId: id }]).present, false, id);
  }
  assert.equal(jsonStatus([{ ...goodDevice, service: 'WinUSB', guids: [] }, {
    ...goodDevice, instanceId: 'USB\\VID_04DA&PID_2370&MI_00\\X', service: 'libusbK',
  }]).ok, false);
});

test('realistic en-US and zh-CN pnputil output uses instance IDs, never translated labels or status', () => {
  const en = parsePnputil(fs.readFileSync(path.join(__dirname, 'fixtures/pnputil-en-US.txt'), 'utf8'));
  assert.equal(en.present, true);
  assert.equal(en.normalPresent, true);
  assert.equal(en.devices.length, 1);
  assert.equal(en.ok, false);
  const zh = parsePnputil(fs.readFileSync(path.join(__dirname, 'fixtures/pnputil-zh-CN.txt'), 'utf8').replaceAll('\n', '\r\n'));
  assert.equal(zh.present, true);
  assert.equal(zh.normalPresent, false);
  assert.equal(zh.devices.length, 1);
  assert.match(zh.devices[0].instanceId, /MI_00/);
  assert.equal(zh.ok, false);
  assert.equal(zh.guidRegistered, null);
  const stableService = parsePnputil(`实例 ID： ${instanceId}\n服务： WinUSB\n`);
  assert.equal(stableService.driver, 'WinUSB');
  assert.equal(stableService.ok, false); // pnputil /ids cannot prove the registered GUID.
  assert.equal(parsePnputil('Hardware IDs:\n USB\\VID_04DA&PID_2370').present, false);
});

test('status prefers JSON; falls back to pnputil without claiming readiness; failures remain unknown', async () => {
  const calls = [];
  const manager = new DriverManager({ platform: 'win32', run: async (exe, args) => {
    calls.push({ exe, args });
    return { code: 0, stdout: JSON.stringify([goodDevice]), stderr: '' };
  } });
  assert.equal((await manager.status()).ok, true);
  assert.equal(calls.length, 1);
  assert.match(calls[0].exe, /WindowsPowerShell.*powershell.exe/);
  const script = Buffer.from(calls[0].args.at(-1), 'base64').toString('utf16le');
  assert.match(script, /Get-PnpDevice -PresentOnly/);
  assert.ok(!script.includes('RunAs'));
  manager.run = async (_exe, args) => args[0] === '-NoProfile'
    ? { code: 1, stdout: '', stderr: 'PnP unavailable' }
    : { code: 0, stdout: fs.readFileSync(path.join(__dirname, 'fixtures/pnputil-zh-CN.txt'), 'utf8'), stderr: '' };
  const fallback = await manager.status();
  assert.equal(fallback.source, 'pnputil');
  assert.equal(fallback.present, true);
  assert.equal(fallback.ok, false);
  assert.equal(fallback.driverDetectable, false);
  assert.match(fallback.warning, /PnP unavailable/);
  manager.run = async () => ({ code: 1, stdout: '', stderr: 'access denied' });
  const failed = await manager.status();
  assert.equal(failed.present, null);
  assert.match(failed.error, /access denied/);
});

test('non-Windows status/install/uninstall never spawn processes', async () => {
  const manager = new DriverManager({ platform: 'darwin', run: () => { throw new Error('must not run'); } });
  assert.deepEqual(await manager.status(), { supported: false });
  for (const action of ['install', 'uninstall']) assert.equal((await manager.change(action)).supported, false);
});

function elevatedInvocation(args) {
  const wrapper = Buffer.from(args.at(-1), 'base64').toString('utf16le');
  assert.match(wrapper, /Start-Process.*-Verb RunAs -Wait -PassThru/);
  assert.match(wrapper, /NativeErrorCode -eq 1223/);
  const encoded = /'-EncodedCommand', '([A-Za-z0-9+/=]+)'/.exec(wrapper)[1];
  const inner = Buffer.from(encoded, 'base64').toString('utf16le');
  const script = /^& '((?:''|[^'])*)'/.exec(inner)[1].replaceAll("''", "'");
  const resultPath = /-ResultPath '((?:''|[^'])*)'/.exec(inner)[1].replaceAll("''", "'");
  return { inner, script, resultPath };
}

test('elevation copies resources from package, safely encodes arguments and reads failure/success JSON', async () => {
  let copied;
  const manager = new DriverManager({ platform: 'win32', run: async (_exe, args, options) => {
    assert.equal(options.timeout, 0); // Never time out while waiting for UAC/user or an active installer.
    copied = elevatedInvocation(args);
    assert.equal(fs.readFileSync(copied.script, 'utf8'), fs.readFileSync(path.join(__dirname, '../driver/install-driver.ps1'), 'utf8'));
    assert.ok(fs.existsSync(path.join(path.dirname(copied.script), 'lumixtool_winusb.inf')));
    fs.writeFileSync(copied.resultPath, '\uFEFF' + JSON.stringify({ ok: false, step: 'pnputil', message: '签名不受信任', pnputilExit: 5, output: 'Windows 原始错误' }));
    return { code: 0, stdout: '', stderr: '' };
  } });
  const failure = await manager.change('install');
  assert.equal(failure.ok, false);
  assert.equal(failure.pnputilExit, 5);
  assert.equal(failure.output, 'Windows 原始错误');
  assert.equal(fs.existsSync(path.dirname(copied.script)), false);
  manager.run = async (_exe, args) => {
    copied = elevatedInvocation(args);
    assert.match(copied.inner, /uninstall-driver.ps1/);
    assert.match(copied.inner, /-RemoveCertificate$/);
    fs.writeFileSync(copied.resultPath, JSON.stringify({ ok: true, step: 'complete', message: 'removed', pnputilExit: 3010, output: '' }));
    return { code: 0 };
  };
  assert.equal((await manager.change('uninstall', { removeCertificate: true })).ok, true);
  assert.equal(fs.existsSync(path.dirname(copied.script)), false);
});

test('UAC cancellation, failed launch, malformed result and missing packaged resources return structured errors', async () => {
  let copied;
  const manager = new DriverManager({ platform: 'win32', run: async (_exe, args) => {
    copied = elevatedInvocation(args);
    assert.ok(!copied.inner.includes('-RemoveCertificate'));
    return { code: 1223, stdout: '', stderr: '' };
  } });
  const cancelled = await manager.change('uninstall', { removeCertificate: 'true' });
  assert.equal(cancelled.cancelled, true);
  assert.equal(cancelled.ok, false);
  assert.equal(fs.existsSync(path.dirname(copied.script)), false);
  manager.run = async () => ({ code: 1, stdout: '', stderr: 'cannot elevate' });
  assert.equal((await manager.change('install')).cancelled, false);
  manager.run = async () => { throw new Error('powershell missing'); };
  assert.match((await manager.change('install')).message, /powershell missing/);
  for (const invalid of ['not JSON', '{"ok":true}']) {
    manager.run = async (_exe, args) => {
      copied = elevatedInvocation(args);
      fs.writeFileSync(copied.resultPath, invalid);
      return { code: 0 };
    };
    assert.equal((await manager.change('install')).ok, false);
    assert.equal(fs.existsSync(path.dirname(copied.script)), false);
  }
  manager.directory = path.join(os.tmpdir(), 'LumixTool-nonexistent-resource');
  assert.equal((await manager.change('install')).step, 'launch');
});

test('output decoding handles UTF-8 and UTF-16 pnputil variants', () => {
  assert.equal(decodeOutput(Buffer.from('驱动程序名称: WinUSB')), '驱动程序名称: WinUSB');
  assert.equal(decodeOutput(Buffer.from('\uFEFF实例 ID: USB\\VID_04DA&PID_2370\\X', 'utf16le')), '实例 ID: USB\\VID_04DA&PID_2370\\X');
});

test('driver INF and scripts have the fixed scope, GUID, result contract and no bundled payloads (static only)', () => {
  const directory = path.join(__dirname, '../driver');
  const inf = fs.readFileSync(path.join(directory, 'lumixtool_winusb.inf'), 'utf8');
  assert.match(inf, /Class=USBDevice/);
  assert.match(inf, /ClassGuid=\{88BAE032-5A81-49f0-BC3D-A4FF138216D6\}/);
  assert.match(inf, /DeviceInterfaceGUIDs,0x10000,"\{CDE53111-593A-43C9-AB10-EA9DACF2C573\}"/);
  for (const architecture of ['NTamd64', 'NTarm64', 'NTx86']) {
    const section = inf.replace(/\r\n/g, '\n').split(`[Models.${architecture}]`)[1].split('\n[')[0];
    assert.ok(section.includes('USB\\VID_04DA&PID_2370\n'));
    assert.ok(section.includes('USB\\VID_04DA&PID_2370&MI_00'));
  }
  assert.ok(!inf.includes('2382'));
  assert.match(inf, /Needs=WINUSB.NT.Services/);
  assert.ok(!/CoInstallers|CopyFiles|\.sys/i.test(inf));
  for (const name of ['install-driver.ps1', 'uninstall-driver.ps1']) {
    const script = fs.readFileSync(path.join(directory, name), 'utf8');
    assert.match(script, /finally\s*\{/);
    assert.match(script, /\[IO.File\]::WriteAllText\(\$ResultPath/);
    for (const key of ['ok', 'step', 'message', 'pnputilExit', 'output']) assert.ok(script.includes(key));
    assert.ok(!/Invoke-WebRequest|Invoke-RestMethod|https?:|bcdedit|testsigning/i.test(script));
    assert.ok(!/[^\x00-\x7F]/.test(script), 'Windows PowerShell 5.1 scripts must stay ASCII or use a UTF-8 BOM');
  }
  const install = fs.readFileSync(path.join(directory, 'install-driver.ps1'), 'utf8');
  assert.match(install, /New-FileCatalog.*-CatalogVersion 2/);
  assert.match(install, /Set-AuthenticodeSignature.*-HashAlgorithm SHA256/);
  assert.match(install, /New-SelfSignedCertificate -Type CodeSigningCert/);
  const uninstall = fs.readFileSync(path.join(directory, 'uninstall-driver.ps1'), 'utf8');
  assert.match(uninstall, /\$published -and \$original -and \$provider/);
  assert.match(uninstall, /if \(\$RemoveCertificate\)/);
  assert.match(uninstall, /-DeleteKey/);
  assert.ok(fs.readdirSync(directory).every(name => /\.(inf|ps1)$/.test(name)));
});

test('driver UI states cover missing/normal mode and never present unverified GUIDs as healthy', async () => {
  const { driverState, needsDriverSetup } = await import('../src/components/driverState.mjs');
  assert.match(driverState({ supported: false }).title, /仅支持 Windows/);
  assert.match(driverState({ supported: true, present: false }).title, /未检测到服务模式/);
  assert.match(driverState({ supported: true, present: false, normalPresent: true }).title, /2382/);
  const missing = { supported: true, present: true, ok: false, winusb: false };
  assert.equal(needsDriverSetup(missing), true);
  assert.match(driverState(missing).title, /未安装驱动/);
  assert.match(driverState({ ...missing, winusb: true, guidRegistered: null }).title, /尚无法确认/);
  assert.match(driverState({ ...missing, winusb: true, guidRegistered: false }).title, /GUID 缺失/);
  assert.equal(driverState({ ...missing, ok: true }).type, 'success');
  assert.equal(needsDriverSetup({ ...missing, error: 'failed' }), false);
  assert.equal(driverState({ ...missing, error: 'failed' }).type, 'warning');
  assert.match(driverState({ ...missing, driverDetectable: false }).title, /尚无法确认/);
  assert.equal(needsDriverSetup({ ...missing, driverDetectable: false }), false);
});
