const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const { Runtime, lineReader, parseResult } = require('../runtime');
const { START, END } = require('../memory.mjs');

function fixture(t, options = {}) {
  const directory = fs.mkdtempSync(path.join(__dirname, '.runtime-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return {
    directory,
    options: {
      configPath: path.join(directory, 'LumixTool', 'config.json'),
      legacyConfigPath: path.join(directory, 's5-focus-sound', 'config.json'),
      scriptPath: path.join(directory, 's5focus.py'),
      ...options,
    },
  };
}

test('legacy config is copied on first run and never overwrites a new config', t => {
  const { options } = fixture(t);
  fs.mkdirSync(path.dirname(options.legacyConfigPath), { recursive: true });
  const oldConfig = { python: 'C:\\Python313\\python.exe', extra: 'preserved' };
  fs.writeFileSync(options.legacyConfigPath, JSON.stringify(oldConfig));
  const first = new Runtime(options);
  assert.deepEqual(first.loadConfig(), oldConfig);
  assert.deepEqual(JSON.parse(fs.readFileSync(options.legacyConfigPath)), oldConfig);
  fs.writeFileSync(options.configPath, JSON.stringify({ python: '/new/python3' }));
  assert.equal(new Runtime(options).loadConfig().python, '/new/python3');
});

test('line reader handles split progress, CRLF, multibyte UTF-8 and unterminated JSON', () => {
  const lines = [];
  const reader = lineReader(line => lines.push(line));
  const wire = Buffer.from('PROGRESS 2000 44100\r\nPROGRESS 4000 44100\n{"ok":false,"error":"连接失败"}');
  for (let index = 0; index < wire.length; index++) reader.write(wire.subarray(index, index + 1));
  reader.end();
  assert.deepEqual(lines, ['PROGRESS 2000 44100', 'PROGRESS 4000 44100', '{"ok":false,"error":"连接失败"}']);
});

test('last stdout JSON is parsed independently from stderr; errors remain visible', () => {
  assert.deepEqual(parseResult({ code: 0, stdout: 'PROGRESS 2 2\n{"ok":true}\n', stderr: 'diagnostic' }), { ok: true });
  assert.deepEqual(parseResult({ code: 0, stdout: '{"connected":false}', stderr: '' }), { connected: false });
  assert.equal(parseResult({ code: 1, stdout: '', stderr: 'USB read failed\n' }).error, 'USB read failed');
  assert.equal(parseResult({ code: 0, stdout: '{"ok":false,"error":"camera text"}', stderr: '' }).error, 'camera text');
  assert.match(parseResult({ code: 0, stdout: 'invalid json', stderr: '' }).error, /invalid json/);
  assert.equal(parseResult({ code: 1, stdout: '{"ok":true}', stderr: 'process failed' }).ok, false);
});

test('mock defaults to a connected camera and exposes every connection scenario without Python', async t => {
  const { options } = fixture(t, { mock: true });
  const runtime = new Runtime(options);
  runtime.findPython = () => { throw new Error('mock must not search for Python'); };
  runtime.run = () => { throw new Error('mock must not spawn Python'); };
  assert.deepEqual(await runtime.status(), { connected: true, model: 'DC-S5', body_version: '0x0290', custom: false, verified: true, table_problem: null });
  assert.equal((await runtime.environment()).python, 'Mock · 无需 Python');
  runtime.configureMock({ scenario: 'disconnected' });
  assert.deepEqual(await runtime.status(), { connected: false });
  runtime.configureMock({ scenario: 'error' });
  assert.match((await runtime.status()).error, /模拟 USB/);
  runtime.configureMock({ scenario: 'python-missing' });
  assert.equal((await runtime.environment()).python, null);
  assert.equal((await runtime.status()).pythonMissing, true);
  assert.equal((await runtime.restore()).ok, false);
  runtime.configureMock({ scenario: 'invalid' });
  assert.equal(runtime.mockState.scenario, 'python-missing');
});

test('first mock apply scans then writes, restore emits progress, and failure is one shot', async t => {
  const progress = [];
  const { options } = fixture(t, { mock: true, onProgress: event => progress.push(event) });
  const runtime = new Runtime(options);
  runtime.run = () => { throw new Error('mock must not start backend'); };
  const payload = { pcm: new ArrayBuffer(882), samples: 441 };
  const start = Date.now();
  assert.deepEqual(await runtime.apply(payload), { ok: true });
  assert.ok(Date.now() - start >= 5800);
  assert.ok(progress.some(event => event.phase === 'scan'));
  assert.equal(progress.at(-1).done, 441);
  assert.equal(progress.at(-1).overallDone, 441);
  const scan = progress.filter(event => event.phase === 'scan');
  assert.equal(scan.at(-1).done, (END - START) / 1024);
  assert.equal((await runtime.status()).custom, true);
  progress.length = 0;
  assert.deepEqual(await runtime.restore(), { ok: true });
  assert.deepEqual(progress.at(-1), { done: 32, total: 32 });
  assert.equal((await runtime.status()).custom, false);
  runtime.configureMock({ failNext: true });
  assert.match((await runtime.apply(payload)).error, /USB 传输超时/);
  assert.equal(runtime.mockState.failNext, false);
  assert.equal((await runtime.status()).custom, false);
});

test('bad PCM sizes and sample counts are rejected before starting an operation', async t => {
  const { options } = fixture(t, { mock: true });
  const runtime = new Runtime(options);
  let called = false;
  runtime.mockOperation = () => { called = true; };
  for (const samples of [0, -1, 132301, 2.5, NaN]) {
    assert.equal((await runtime.apply({ pcm: new ArrayBuffer(2), samples })).ok, false);
  }
  assert.equal((await runtime.apply({ pcm: new ArrayBuffer(2), samples: 2 })).error, 'PCM size mismatch');
  assert.equal(called, false);
});

test('non-Windows live mode is cleanly disconnected and cannot invoke WinUSB', async t => {
  const { options } = fixture(t, { platform: 'darwin' });
  const runtime = new Runtime(options);
  runtime.findPython = async () => '/usr/bin/python3';
  runtime.run = () => { throw new Error('must not run the Windows backend'); };
  const status = await runtime.status();
  assert.equal(status.connected, false);
  assert.equal(status.error, undefined);
  assert.match(status.platformNote, /Windows WinUSB/);
  assert.equal((await runtime.apply({ pcm: new ArrayBuffer(2), samples: 1 })).ok, false);
  assert.equal((await runtime.restore()).ok, false);
  runtime.findPython = async () => null;
  assert.equal((await runtime.status()).pythonMissing, true);
});

test('mock controls cannot enable simulation in a live runtime', t => {
  const { options } = fixture(t);
  assert.equal(new Runtime(options).configureMock({ scenario: 'connected' }).ok, false);
});

test('Python transport preserves existing arguments and parses fragmented progress + stdout JSON', async t => {
  const { options } = fixture(t);
  const invocations = [];
  const events = [];
  function spawn(exe, args, spawnOptions) {
    invocations.push({ exe, args, spawnOptions });
    const child = new EventEmitter();
    child.stdout = new PassThrough();
    child.stderr = new PassThrough();
    child.kill = () => {};
    process.nextTick(() => {
      child.stdout.write('PROG');
      child.stdout.write('RESS 2000 4000\r\nPROGRESS 4000');
      child.stdout.write(' 4000\n');
      for (const byte of Buffer.from('{"ok":true,"note":"校验完成"}')) child.stdout.write(Buffer.from([byte]));
      child.stderr.write('separate diagnostic');
      child.emit('close', 0);
    });
    return child;
  }
  const sandbox = {
    module: { exports: {} }, process, Buffer, setTimeout, clearTimeout,
    require: name => name === 'node:child_process' ? { spawn }
      : name === './driver' ? require('../driver')
      : name === './mock-sound-table.json' ? require('../mock-sound-table.json')
      : name === './memory.mjs' ? require('../memory.mjs') : require(name),
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../runtime.js'), 'utf8'), sandbox);
  const runtime = new sandbox.module.exports.Runtime({ ...options, onProgress: event => events.push({ ...event }) });
  runtime.findPython = async () => 'python3';
  const result = await runtime.run(['apply', 'sound.pcm', '4000']);
  assert.equal(result.ok, true);
  assert.equal(result.note, '校验完成');
  assert.deepEqual(Array.from(invocations[0].args), ['-u', options.scriptPath, 'apply', 'sound.pcm', '4000']);
  assert.equal(invocations[0].spawnOptions.windowsHide, true);
  assert.deepEqual(events, [{ done: 2000, total: 4000 }, { done: 4000, total: 4000 }]);
});

test('mock driver states and installation outcomes never spawn Windows tools or require Python', async t => {
  const { options } = fixture(t, { mock: true, platform: 'darwin' });
  const runtime = new Runtime(options);
  runtime.driver.run = () => { throw new Error('mock must not run Windows commands'); };
  runtime.findPython = () => { throw new Error('driver must not require Python'); };
  assert.equal((await runtime.driverStatus()).ok, true);
  for (const driverScenario of ['absent', 'normal', 'missing', 'wrong-driver', 'missing-guid', 'unknown-guid']) {
    runtime.configureMock({ driverScenario });
    const status = await runtime.driverStatus();
    assert.equal(status.ok, false);
    assert.equal(status.present, !['absent', 'normal'].includes(driverScenario));
    assert.equal(status.normalPresent, driverScenario === 'normal');
    assert.equal((await runtime.status()).connected, false);
  }
  runtime.configureMock({ driverScenario: 'missing', driverResult: 'cancelled' });
  assert.equal((await runtime.installDriver()).cancelled, true);
  assert.equal((await runtime.driverStatus()).ok, false);
  runtime.configureMock({ driverResult: 'failure' });
  assert.equal((await runtime.installDriver()).pnputilExit, 5);
  assert.equal((await runtime.driverStatus()).ok, false);
  runtime.configureMock({ driverResult: 'success' });
  assert.equal((await runtime.installDriver()).ok, true);
  assert.equal((await runtime.driverStatus()).ok, true);
  assert.equal((await runtime.status()).connected, true);
  assert.equal((await runtime.installDriver()).ok, true); // Repeated installation is harmless.
  assert.equal((await runtime.uninstallDriver({ removeCertificate: true })).ok, true);
  assert.equal((await runtime.driverStatus()).ok, false);
  runtime.configureMock({ driverScenario: 'normal' });
  assert.equal((await runtime.installDriver()).ok, true); // Staged package does not change camera mode.
  assert.equal((await runtime.driverStatus()).normalPresent, true);
  runtime.configureMock({ driverScenario: 'invalid', driverResult: 'invalid' });
  assert.equal(runtime.mockState.driverScenario, 'normal');
  assert.equal(runtime.mockState.driverResult, 'success');
});
