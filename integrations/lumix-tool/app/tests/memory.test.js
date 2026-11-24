const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { Runtime } = require('../runtime');
const { START, END, liveRegions, memoryStats, planAllocation, markRange, mockMemoryMap, validMap } = require('../memory.mjs');

const scanned = (map = mockMemoryMap(), bodyVersion = '0x0290') => ({ ...map, bodyVersion, scannedAt: '2026-11-22T00:00:00.000Z' });
// The table's +0x14 length is PCM bytes (verified on hardware), i.e. 2 per sample.
const owned = (index, start, samples) => ({ index, addr: start + 16 - 0x80000000, size: samples * 2 });
function fixture(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'lumixtool-memory-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const events = [];
  const runtime = new Runtime({ configPath: path.join(directory, 'config.json'), legacyConfigPath: path.join(directory, 'old.json'),
    mock: true, onProgress: event => events.push(event) });
  runtime.mockOperation = async () => ({ ok: true });
  return { runtime, events };
}

test('malformed or incomplete caches require a scan and cannot drive allocation', () => {
  for (const map of [null, { ...mockMemoryMap(), runs: [null] },
    { ...mockMemoryMap(), runs: mockMemoryMap().runs.slice(1) }, { ...mockMemoryMap(), start: '0x8F000001' }]) {
    assert.equal(validMap(map), false);
    assert.equal(planAllocation(map, [], [1], 100).needsScan, true);
  }
  assert.deepEqual(liveRegions([{ index: 1 }, { index: 2, addr: 'bad', size: 1 }]), []);
});

test('reuse uses dump ownership, rounded capacity and the same start', () => {
  const entries = [owned(1, START + 1024, 600)];
  assert.deepEqual(liveRegions(entries)[0], { index: 1, start: START + 1024, end: START + 3072, capacity: 2048, samples: 600, reusable: true });
  const result = planAllocation(mockMemoryMap(), entries, [1], 1000);
  assert.equal(result.ok, true);
  assert.equal(result.allocations[0].start, START + 1024);
  assert.equal(result.allocations[0].reused, true);
  assert.equal(result.needed, 0);
  const moved = planAllocation(markRange(mockMemoryMap(), START + 1024, START + 3072, 'lumixtool'), entries, [1], 1500);
  assert.equal(moved.allocations[0].reused, false);
  assert.equal(moved.allocations[0].start, START + 3072);
});

test('first fit avoids every other live span and earlier batch allocations; stale data and zero blocks are allocatable', () => {
  const map = mockMemoryMap();
  const entries = [owned(2, START, 100), owned(3, START + 2048, 100)];
  const result = planAllocation(map, entries, [1, 4], 500);
  assert.equal(result.ok, true);
  assert.deepEqual(result.allocations.map(item => item.start), [START + 1024, START + 3072]);
  // Since 730faad the 0x8F scratch keeps stale bytes across warm reboots, so a
  // scanned 'data' run is allocatable; only LumixTool-owned spans are skipped.
  const [firstFree, dataRun] = map.runs;
  assert.deepEqual([firstFree.kind, dataRun.kind], ['free-0x55', 'data']);
  const largeLive = [owned(2, START, (Number(firstFree.end) - START - 16) / 2)];
  assert.equal(planAllocation(map, largeLive, [1], 100).allocations[0].start, Number(dataRun.start));
  const claimed = markRange(map, Number(dataRun.start), Number(dataRun.end), 'lumixtool');
  assert.equal(planAllocation(claimed, largeLive, [1], 100).allocations[0].start, Number(dataRun.end));
  // Legacy unaligned allocations are protected but cannot be reused.
  const legacy = planAllocation(map, [owned(2, START + 256, 500)], [1], 500);
  assert.equal(legacy.allocations[0].start, START + 2048);
  const alias = planAllocation(map, [owned(1, START, 100), owned(2, START, 100)], [1], 100);
  assert.equal(alias.allocations[0].reused, false);
  assert.equal(alias.allocations[0].start, START + 1024);
});

test('live ownership reads the raw table and includes the very first scratch PCM address', () => {
  const raw = Buffer.alloc(32);
  raw.writeUInt32LE(0x0F000010, 4); raw.writeUInt32LE(1200, 0x14); // 600 samples
  const live = liveRegions([{ index: 1, addr: 0, size: 0, hex: raw.toString('hex') }]);
  assert.equal(live[0].start, START);
  assert.equal(live[0].capacity, 2048);
  assert.equal(liveRegions([{ index: 2, addr: 0x0F800000, size: 10 }]).length, 0);
  const stats = memoryStats(mockMemoryMap(), [owned(1, START, 100), owned(2, START, 100)]);
  assert.equal(stats.used, 1024);
  const freeBytes = mockMemoryMap().runs.filter(run => run.kind !== 'lumixtool')
    .reduce((sum, run) => sum + Number(run.end) - Number(run.start), 0);
  assert.equal(stats.totalFree, freeBytes - 1024);
});

test('batch insufficient space reports needed, total and largest before any write', async t => {
  const { runtime } = fixture(t);
  runtime.saveMemoryMap(scanned({ start: '0x8F000000', length: 1024,
    runs: [{ start: '0x8F000000', end: '0x8F000400', kib: 1, kind: 'free-0x55' }] }));
  let writes = 0;
  runtime.applySlot = () => { writes++; throw new Error('must allocate all before writing'); };
  const result = await runtime.soundBatch('apply', { indices: [1, 2], samples: 400, pcm: new ArrayBuffer(800) });
  assert.equal(result.code, 'insufficient-space');
  assert.equal(result.needed, 2048);
  assert.equal(result.totalFree, 1024);
  assert.equal(result.largestFree, 1024);
  assert.deepEqual(result.allocations, []);
  assert.deepEqual(result.succeeded, []);
  assert.match(result.error, /需新分配 2 KiB.*可用 1 KiB.*最大连续可写入 1 KiB/);
  assert.equal(writes, 0);
});

test('fragmented free space can be insufficient despite enough total bytes', () => {
  let map = { start: '0x8F000000', length: 4096, runs: [{ start: '0x8F000000', end: '0x8F001000', kind: 'free-0x55' }] };
  map = markRange(map, START + 1024, START + 3072, 'lumixtool');
  const result = planAllocation(map, [], [1], 600);
  assert.equal(result.ok, false);
  assert.equal(result.totalFree, 2048);
  assert.equal(result.largestFree, 1024);
  assert.equal(planAllocation(null, [], [1], 100).needsScan, true);
});

test('successful writes update the cache, preserve scan time and are reusable by the same entry', async t => {
  const { runtime } = fixture(t);
  runtime.saveMemoryMap(scanned());
  const write = (index, samples) => runtime.soundBatch('apply', { indices: [index], samples, pcm: new ArrayBuffer(samples * 2) });
  assert.equal((await write(1, 100)).ok, true);
  assert.equal((await write(2, 100)).ok, true);
  assert.equal(runtime.mockEntries[1].addr, '0x0F000010');
  assert.equal(runtime.mockEntries[2].addr, '0x0F000410');
  assert.equal((await write(1, 400)).ok, true);
  assert.equal(runtime.mockEntries[1].addr, '0x0F000010');
  const map = runtime.memoryMap('0x0290').map;
  assert.equal(map.runs[0].kind, 'lumixtool');
  assert.equal(map.runs[0].kib, 2);
  assert.equal(map.scannedAt, '2026-11-22T00:00:00.000Z');
  assert.equal(runtime.memoryMap('0x0280').map, null);
  const restarted = new Runtime({ configPath: runtime.configPath, legacyConfigPath: runtime.legacyConfigPath, mock: true });
  assert.deepEqual(restarted.memoryMap('0x0290').map, map);
});

test('stale guard refusal marks the allocation LumixTool-owned, stops the batch and never retries', async t => {
  const { runtime } = fixture(t);
  runtime.saveMemoryMap(scanned());
  runtime.configureMock({ scenario: 'region-not-free' });
  const before = runtime.mockEntries.map(entry => entry.hex);
  let calls = 0;
  const applySlot = runtime.applySlot.bind(runtime);
  runtime.applySlot = payload => { calls++; return applySlot(payload); };
  const result = await runtime.soundBatch('apply', { indices: [1, 2], samples: 600, pcm: new ArrayBuffer(1200) });
  assert.equal(result.rescan, true);
  assert.equal(result.code, 'stale-map');
  assert.equal(result.address, '0x8F000000');
  assert.match(result.error, /未写入.*重新扫描/);
  assert.equal(calls, 1);
  assert.deepEqual(runtime.mockEntries.map(entry => entry.hex), before);
  const map = runtime.memoryMap('0x0290').map;
  assert.equal(map.runs[0].kind, 'lumixtool');
  assert.equal(map.runs[0].kib, 2);
  assert.equal(planAllocation(map, runtime.mockEntries, [2], 600).allocations[0].start, START + 2048);
});

test('a later guard failure preserves earlier success and stops all remaining writes', async t => {
  const { runtime } = fixture(t);
  runtime.saveMemoryMap(scanned());
  const applySlot = runtime.applySlot.bind(runtime);
  runtime.applySlot = payload => {
    if (payload.index === 2) {
      // Another entry's header appeared at #2's span after the scan.
      const at = payload.regionAddr - START;
      runtime.mockRam.write('LMXTSLOT', at);
      runtime.mockRam.writeUInt32LE(9, at + 8);
      runtime.mockRam.writeUInt32LE(1, at + 12);
    }
    return applySlot(payload);
  };
  const result = await runtime.soundBatch('apply', { indices: [1, 2, 3], samples: 100, pcm: new ArrayBuffer(200) });
  assert.deepEqual(result.succeeded, [1]);
  assert.equal(result.failedIndex, 2);
  assert.deepEqual(result.pending, [3]);
  // #1's span and the refused #2 span are both LumixTool-owned now.
  const runs = runtime.memoryMap('0x0290').map.runs;
  assert.equal(runs[0].kind, 'lumixtool');
  assert.equal(Number(runs[0].end), START + 2048);
});

test('mock scan is read-only, takes about 3 seconds, emits a scan phase and caches by body version', async t => {
  const { runtime, events } = fixture(t);
  runtime.run = () => { throw new Error('must not start Python'); };
  const before = Buffer.from(runtime.mockRam);
  const start = Date.now();
  const result = await runtime.scanMemory();
  assert.ok(Date.now() - start >= 2900);
  assert.equal(result.ok, true);
  assert.equal(runtime.mockRam.equals(before), true);
  assert.deepEqual(result.map.runs, mockMemoryMap().runs);
  assert.ok(events.every(event => event.phase === 'scan'));
  assert.equal(events.at(-1).done, (END - START) / 1024);
  assert.equal(events.at(-1).total, (END - START) / 1024);
  assert.equal(result.map.bodyVersion, '0x0290');
  assert.ok(!Number.isNaN(Date.parse(result.map.scannedAt)));
  assert.equal(validMap(result.map), true);
  assert.equal(Number(result.map.start) + result.map.length, END);
  assert.equal(runtime.progressPhase, null);
});

test('live writes scan first when this body has no map and pass an explicit address', async t => {
  const { runtime, events } = fixture(t);
  runtime.mock = false;
  runtime.platform = 'win32';
  const stock = require('../mock-sound-table.json');
  const calls = [];
  runtime.run = async args => {
    calls.push(args[0]);
    if (args[0] === 'status') return { connected: true, body_version: '0x0290' };
    if (args[0] === 'dump') return { ok: true, entries: stock };
    if (args[0] === 'scan') { runtime.emitProgress({ done: 8192, total: 8192 }); return { ok: true, ...mockMemoryMap() }; }
    assert.equal(args[0], 'apply-slot');
    assert.equal(args[4], '0x8F000000');
    assert.equal(fs.readFileSync(args[2]).length, 200);
    return { ok: true };
  };
  assert.equal((await runtime.soundBatch('apply', { indices: [1], samples: 100, pcm: new ArrayBuffer(200) })).ok, true);
  assert.ok(calls.indexOf('scan') < calls.indexOf('apply-slot'));
  assert.ok(events.some(event => event.phase === 'scan'));
  assert.equal(runtime.memoryMap('0x0280').map, null);
  assert.equal(runtime.memoryMap('0x0290').map.runs[0].kind, 'lumixtool');
});

test('adjacent writable runs of different kinds merge into one contiguous range', () => {
  const map = mockMemoryMap();
  const stats = memoryStats(map, [owned(1, START, 100)]);
  // Everything except #1's 1 KiB is writable and contiguous.
  assert.equal(stats.largestFree, END - START - 1024);
  assert.equal(stats.totalFree, END - START - 1024);
  const big = planAllocation(map, [owned(1, START, 100)], [2], 132300);
  assert.equal(big.ok, true);
  assert.equal(big.allocations[0].start, START + 1024);
});
