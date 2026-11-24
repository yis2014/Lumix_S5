// Shared by the main process and renderer: plans are advisory until the
// backend guards the exact bytes. All intervals use an exclusive end.
export const START = 0x8F000000;
export const END = 0x8F800000;
export const BLOCK = 1024;
export const KINDS = ['free-0x55', 'lumixtool', 'data', 'zero'];
export const hexAddress = value => `0x${Number(value).toString(16).padStart(8, '0').toUpperCase()}`;
export const roundUp = value => Math.ceil(value / BLOCK) * BLOCK;
export const requiredBytes = samples => roundUp(16 + samples * 2);
const overlaps = (a, b) => a.start < b.end && b.start < a.end;
const run = (start, end, kind) => ({ start: hexAddress(start), end: hexAddress(end), kind, kib: (end - start) / BLOCK });

export function validMap(map) {
  if (!map || !Number.isInteger(map.length) || map.length <= 0 || map.length % BLOCK ||
      !Number.isInteger(Number(map.start)) || Number(map.start) % BLOCK ||
      Number(map.start) < START || Number(map.start) + map.length > END || !Array.isArray(map.runs)) return false;
  let cursor = Number(map.start);
  for (const item of map.runs) {
    if (!item || typeof item !== 'object' || Number(item.start) !== cursor || !Number.isInteger(Number(item.end)) ||
        Number(item.end) <= cursor || Number(item.end) % BLOCK || !KINDS.includes(item.kind)) return false;
    cursor = Number(item.end);
  }
  return cursor === Number(map.start) + map.length;
}

export function liveRegions(entries = []) {
  return entries.flatMap(entry => {
    // dump's 32 bytes are authoritative, including in the presence of stale UI fields.
    // The table stores the PCM length in BYTES at +0x14 (verified on hardware).
    let pcm = Number(entry.addr), bytes = Number(entry.size);
    if (typeof entry.hex === 'string' && /^[0-9a-f]{64}$/i.test(entry.hex)) {
      const bytesArr = Uint8Array.from(entry.hex.match(/../g), part => parseInt(part, 16));
      const view = new DataView(bytesArr.buffer);
      pcm = view.getUint32(4, true);
      bytes = view.getUint32(0x14, true);
    }
    pcm += 0x80000000;
    if (!Number.isInteger(pcm) || !Number.isInteger(bytes) || bytes < 0 || pcm < START || pcm >= END) return [];
    const samples = bytes / 2;
    const start = Math.max(START, pcm - 16);
    const end = Math.min(END, roundUp(pcm + bytes));
    return [{ index: entry.index, start, end, capacity: end - start, samples,
      reusable: pcm - 16 >= START && start % BLOCK === 0 && bytes > 0 && pcm + bytes <= END }];
  });
}

function freeRanges(map, excluded = []) {
  if (!validMap(map)) return [];
  const ranges = [];
  for (const item of map.runs.filter(item => item.kind !== 'lumixtool')) {
    let parts = [{ start: Number(item.start), end: Number(item.end) }];
    for (const occupied of excluded) {
      parts = parts.flatMap(part => !overlaps(part, occupied) ? [part] : [
        { start: part.start, end: Math.max(part.start, Math.floor(occupied.start / BLOCK) * BLOCK) },
        { start: Math.min(part.end, roundUp(occupied.end)), end: part.end },
      ].filter(part => part.end > part.start));
    }
    ranges.push(...parts);
  }
  // Since 730faad free-0x55, zero and data runs are all writable, so adjacent
  // runs of different kinds form one contiguous writable range.
  ranges.sort((a, b) => a.start - b.start);
  return ranges.reduce((merged, range) => {
    const last = merged.at(-1);
    if (last && range.start <= last.end) last.end = Math.max(last.end, range.end);
    else merged.push({ ...range });
    return merged;
  }, []);
}

export function memoryStats(map, entries = []) {
  const live = liveRegions(entries);
  const free = freeRanges(map, live);
  const sizes = Object.fromEntries(KINDS.map(kind => [kind, 0]));
  if (validMap(map)) {
    const effective = live.reduce((current, item) => markRange(current, item.start, item.end, 'lumixtool'), map);
    for (const item of effective.runs) sizes[item.kind] += Number(item.end) - Number(item.start);
  }
  // Union live intervals: shared/legacy pointers must not double count usage.
  let used = 0, previousEnd = START;
  for (const item of [...live].sort((a, b) => a.start - b.start)) {
    used += Math.max(0, item.end - Math.max(previousEnd, item.start));
    previousEnd = Math.max(previousEnd, item.end);
  }
  return { totalFree: free.reduce((sum, item) => sum + item.end - item.start, 0),
    largestFree: Math.max(0, ...free.map(item => item.end - item.start)),
    used, data: sizes.data, zero: sizes.zero, marked: sizes.lumixtool };
}

export function planAllocation(map, entries, indices, samples) {
  if (!Array.isArray(indices) || !indices.length || indices.some(i => !Number.isInteger(i) || i < 0 || i > 27) ||
      new Set(indices).size !== indices.length || !Number.isInteger(samples) || samples < 1 || samples > 132300) {
    return { ok: false, error: '请选择有效的音效编号和采样数量。', allocations: [] };
  }
  if (!validMap(map)) return { ok: false, needsScan: true, allocations: [], error: '首次写入会先扫描内存。' };
  const live = liveRegions(entries);
  const stats = memoryStats(map, entries);
  const need = requiredBytes(samples);
  const allocations = [];
  const reusable = new Map(indices.map(index => [index, live.find(item => item.index === index && item.reusable && item.capacity >= need &&
    !live.some(other => other.index !== index && overlaps(item, other)))]));
  const needed = indices.filter(index => !reusable.get(index)).length * need;
  for (const index of indices) {
    let chosen = reusable.get(index);
    if (!chosen) {
      const available = freeRanges(map, [...live.filter(item => item.index !== index), ...allocations]);
      const fit = available.find(item => item.end - item.start >= need);
      if (!fit) return { ok: false, code: 'insufficient-space', allocations: [], need, needed, ...stats,
        error: `内存空间不足：需新分配 ${needed / BLOCK} KiB（每项 ${need / BLOCK} KiB）；可用 ${stats.totalFree / BLOCK} KiB，最大连续可写入 ${stats.largestFree / BLOCK} KiB。请减少音效数量或时长，或重新扫描内存。` };
      chosen = fit;
    }
    allocations.push({ index, start: chosen.start, end: chosen.start + need, bytes: need,
      address: hexAddress(chosen.start), reused: !!reusable.get(index) });
  }
  return { ok: true, allocations, need, needed, ...stats };
}

export function markRange(map, start, end, kind) {
  if (!validMap(map) || !KINDS.includes(kind)) throw new Error('内存扫描数据无效，请重新扫描。');
  start = Math.floor(start / BLOCK) * BLOCK;
  end = roundUp(end);
  const parts = map.runs.flatMap(item => {
    const a = Number(item.start), b = Number(item.end);
    if (b <= start || a >= end) return [run(a, b, item.kind)];
    return [a < start && run(a, start, item.kind), run(Math.max(a, start), Math.min(b, end), kind),
      b > end && run(end, b, item.kind)].filter(Boolean);
  });
  const runs = [];
  for (const item of parts) {
    const previous = runs.at(-1);
    if (previous?.kind === item.kind && previous.end === item.start) {
      previous.end = item.end;
      previous.kib += item.kib;
    } else runs.push(item);
  }
  return { ...map, runs };
}

export function mockMemoryMap() {
  const span = END - START;
  const edge = fraction => START + Math.floor((span * fraction) / BLOCK) * BLOCK;
  const edges = [START, edge(0.2), edge(0.3), edge(0.45), edge(0.8), END];
  const kinds = ['free-0x55', 'data', 'zero', 'free-0x55', 'data'];
  return { start: hexAddress(START), length: END - START,
    runs: kinds.map((kind, i) => run(edges[i], edges[i + 1], kind)) };
}
