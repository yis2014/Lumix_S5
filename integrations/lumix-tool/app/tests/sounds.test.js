const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { Runtime } = require('../runtime');
const stock = require('../mock-sound-table.json');
const { mockMemoryMap } = require('../memory.mjs');

function fixture(t, options = {}) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'lumixtool-test-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const runtime = new Runtime({ configPath: path.join(directory, 'config.json'),
    legacyConfigPath: path.join(directory, 'old.json'), scriptPath: 'unused.py', mock: true, ...options });
  runtime.findPython = () => { throw new Error('mock must not look for Python'); };
  runtime.run = () => { throw new Error('mock must not spawn Python'); };
  return runtime;
}
function fastOperations(runtime) {
  runtime.saveMemoryMap({ ...mockMemoryMap(), scannedAt: new Date().toISOString(), bodyVersion: '0x0290' });
  runtime.mockOperation = async (_kind, total) => {
    runtime.emitProgress({ done: Math.floor(total / 2), total });
    runtime.emitProgress({ done: total, total });
    return { ok: true };
  };
}
function patchEntry(runtime, index, address = 0x0F000100) {
  const entry = runtime.mockEntries[index];
  const raw = Buffer.from(entry.hex, 'hex');
  raw.writeUInt32LE(address, 4);
  raw.writeUInt32LE(200, 0x14);
  Object.assign(entry, { addr: `0x${address.toString(16)}`, size: 200, hex: raw.toString('hex') });
}

test('connect backs up 28 entries by body version; originals and labels survive restarts', async t => {
  const runtime = fixture(t);
  let table = (await runtime.inspect()).soundTable;
  assert.equal(table.ok, true);
  assert.equal(table.entries.length, 28);
  assert.equal(Object.keys(table.originals).length, 28);
  assert.deepEqual(table.entries.map(e => e.size), [24064,14464,14464,14464,41216,95104,152704,200704,18304,47104,20736,8064,8064,8064,19200,19200,14464,19200,24064,24064,19328,25088,28928,3072,18304,18048,102400,22400]);
  const original = table.originals[1];
  patchEntry(runtime, 1);
  const device = await runtime.inspect();
  assert.equal(device.custom, true);
  assert.equal(device.soundTable.originals[1], original);
  assert.notEqual(device.soundTable.entries[1].hex, original);
  assert.equal(runtime.renameSound({ version: '0x0290', index: 1, label: '我的对焦音' }).ok, true);
  const restarted = new Runtime({ configPath: runtime.configPath, legacyConfigPath: runtime.legacyConfigPath, mock: true });
  table = (await restarted.inspect()).soundTable;
  assert.equal(table.originals[1], original);
  assert.equal(table.labels[1], '我的对焦音');
  const other = await runtime.soundTable('0x0280');
  assert.equal(other.originals[1], undefined);
  assert.equal(other.labels[1], undefined);
  assert.equal(Object.keys(other.originals).length, 27);
  assert.ok(fs.existsSync(path.join(path.dirname(runtime.configPath), 'sounds-mock.json')));
  assert.ok(!fs.existsSync(path.join(path.dirname(runtime.configPath), 'sounds.json')));
});

test('patched legacy/new addresses without originals are neither saved nor individually restored', async t => {
  const runtime = fixture(t);
  patchEntry(runtime, 1);
  patchEntry(runtime, 27, 0x0F738110);
  patchEntry(runtime, 26, 0x0B5B0110); // scratch briefly used in commit e59b596
  const table = (await runtime.inspect()).soundTable;
  assert.equal(table.originals[1], undefined);
  assert.equal(table.originals[27], undefined);
  assert.equal(table.originals[26], undefined);
  assert.equal(Object.keys(table.originals).length, 25);
  let called = false;
  runtime.restoreId = async () => { called = true; };
  assert.equal((await runtime.soundBatch('restore', { indices: [1] })).ok, false);
  assert.equal(called, false);
});

test('batch regions are independent, progress is overall and per-entry, restoration uses exact saved bytes', async t => {
  const events = [];
  const runtime = fixture(t, { onProgress: event => events.push(event) });
  fastOperations(runtime);
  const result = await runtime.soundBatch('apply', { indices: [1, 0, 27], pcm: new ArrayBuffer(20), samples: 10 });
  assert.deepEqual(result, { ok: true, succeeded: [1, 0, 27] });
  assert.equal(runtime.mockEntries[1].addr, '0x0F000010');
  assert.equal(runtime.mockEntries[0].addr, '0x0F000410');
  assert.equal(runtime.mockEntries[27].addr, '0x0F000810');
  assert.equal(runtime.mockEntries[1].size, 20); // table length is PCM bytes
  assert.ok(events.every(e => e.overallTotal === 30));
  assert.ok(events.every((e, i) => i === 0 || e.overallDone >= events[i - 1].overallDone));
  assert.deepEqual(events.map(e => e.index).filter((e, i, arr) => i === 0 || e !== arr[i - 1]), [1, 0, 27]);
  assert.equal(events.at(-1).overallDone, 30);
  assert.equal(runtime.batchContext, null);
  assert.equal((await runtime.soundBatch('restore', { indices: [1] })).ok, true);
  assert.equal(runtime.mockEntries[1].hex, stock[1].hex);
  assert.equal((await runtime.soundBatch('restore')).succeeded.length, 28);
  assert.deepEqual(runtime.mockEntries, stock);
});

test('stale map refuses the first allocation and leaves all entries untouched', async t => {
  const runtime = fixture(t);
  fastOperations(runtime);
  runtime.configureMock({ scenario: 'region-not-free' });
  const before = runtime.mockEntries.map(e => ({ ...e }));
  const result = await runtime.soundBatch('apply', { indices: [1, 20, 21], pcm: new ArrayBuffer(20), samples: 10 });
  assert.equal(result.ok, false);
  assert.equal(result.code, 'stale-map');
  assert.match(result.error, /重新扫描内存/);
  assert.equal(result.address, '0x8F000000');
  assert.deepEqual(result.succeeded, []);
  assert.equal(result.failedIndex, 1);
  assert.deepEqual(result.pending, [20, 21]);
  assert.deepEqual(runtime.mockEntries[20], before[20]);
  assert.deepEqual(runtime.mockEntries[21], before[21]);
  assert.deepEqual(runtime.mockEntries, before);
  assert.equal(runtime.batchContext, null);
});

test('restore all skips missing originals and stops on first restore failure', async t => {
  const runtime = fixture(t);
  patchEntry(runtime, 2);
  const calls = [];
  runtime.restoreId = async index => { calls.push(index); return { ok: index !== 3, error: 'restore failed' }; };
  const result = await runtime.soundBatch('restore');
  assert.deepEqual(calls, [0, 1, 3]);
  assert.deepEqual(result.succeeded, [0, 1]);
  assert.equal(result.failedIndex, 3);
  assert.ok(!result.pending.includes(2));
});

test('invalid batches, changed versions and corrupt backups cause no writes', async t => {
  const runtime = fixture(t);
  let writes = 0;
  runtime.applySlot = async () => { writes++; return { ok: true }; };
  const payload = { samples: 1, pcm: new ArrayBuffer(2) };
  for (const indices of [[], [28], [-1], [1, 1], ['1'], null]) {
    assert.equal((await runtime.soundBatch('apply', { ...payload, indices })).ok, false);
  }
  assert.equal((await runtime.soundBatch('apply', { ...payload, indices: [1], version: '0x0280' })).ok, false);
  fs.writeFileSync(runtime.soundsPath, 'broken json');
  const result = await runtime.soundBatch('apply', { ...payload, indices: [1] });
  assert.match(result.error, /无法读取音效备份/);
  assert.equal(fs.readFileSync(runtime.soundsPath, 'utf8'), 'broken json');
  assert.equal(writes, 0);
});

test('live slot commands preserve arguments and clean PCM temporary files', async t => {
  const runtime = fixture(t, { mock: false, platform: 'win32' });
  const payload = { index: 20, regionAddr: 0x8F000400, pcm: new Uint8Array([1, 0, 2, 0]), samples: 2 };
  let filename;
  runtime.run = async args => {
    if (args[0] === 'apply-slot') {
      assert.equal(args[1], '20');
      filename = args[2];
      assert.equal(args[3], '2');
      assert.equal(args[4], '0x8F000400');
      assert.deepEqual(fs.readFileSync(filename), Buffer.from(payload.pcm));
    } else assert.deepEqual(args, ['restore-id', '20', stock[20].hex]);
    return { ok: true };
  };
  assert.equal((await runtime.applySlot(payload)).ok, true);
  assert.equal(fs.existsSync(filename), false);
  assert.equal((await runtime.restoreId(20, stock[20].hex)).ok, true);
});

test('renderer state uses saved duration and recognizes both scratch layouts', async () => {
  const { slotState, originalSamples } = await import('../src/tools/sounds/state.mjs');
  assert.equal(originalSamples(stock[1].hex), 7232); // +0x14 = 14464 bytes
  assert.equal(originalSamples(undefined), null);
  assert.equal(slotState(stock[1], stock[1].hex), '原厂');
  assert.equal(slotState({ ...stock[1], addr: '0x0F000100' }, undefined), '已替换');
  assert.equal(slotState({ ...stock[1], addr: '0x0F084110' }, stock[1].hex), '已替换');
  assert.equal(slotState({ ...stock[1], addr: '0x0B5B0100' }, stock[1].hex), '已替换'); // written while scratch was 0x8B5B0000
  assert.equal(slotState(stock[1], stock[2].hex), '未知');
  assert.equal(slotState({}, undefined), '未知');
});

test('unverified firmware reports itself and refuses writes without touching the camera', async t => {
  const runtime = fixture(t);
  fastOperations(runtime);
  assert.equal(runtime.configureMock({ scenario: 'unverified' }).ok, true);
  const status = await runtime.status();
  assert.equal(status.verified, false);
  assert.equal(status.body_version, '0x0280');
  const ram = Buffer.from(runtime.mockRam);
  const entries = JSON.stringify(runtime.mockEntries);
  const payload = { indices: [1], samples: 2, pcm: new Uint8Array([1, 0, 2, 0]).buffer };
  const result = await runtime.soundBatch('apply', { ...payload, version: '0x0280' });
  assert.equal(result.ok, false);
  assert.equal(runtime.mockRam.equals(ram), true);
  assert.equal(JSON.stringify(runtime.mockEntries), entries);
});
