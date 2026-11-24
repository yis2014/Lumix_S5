import { START, END } from '../../../memory.mjs';

// Current scratch RAM (virtual addresses) plus the 0x8B5B0000 range that was
// briefly used (commit e59b596): entries patched there stay replaced until the
// battery is pulled.
export const SCRATCH_VIRTUAL = START - 0x80000000;
const SCRATCH_RANGES = [[SCRATCH_VIRTUAL, END - 0x80000000], [0x0B5B0000, 0x0BAD0000]];
const inScratch = addr => SCRATCH_RANGES.some(([start, end]) => addr >= start && addr < end);

export function originalSamples(hex) {
  if (typeof hex !== 'string' || !/^[0-9a-f]{64}$/i.test(hex)) return null;
  const bytes = Uint8Array.from(hex.match(/../g), byte => parseInt(byte, 16));
  // The table stores PCM length in bytes at +0x14; the UI works in samples.
  return new DataView(bytes.buffer).getUint32(0x14, true) / 2;
}

export function slotState(entry, original) {
  if (!entry?.hex) return '未知';
  if (inScratch(Number(entry.addr))) return '已替换';
  return original && entry.hex.toLowerCase() === original.toLowerCase() ? '原厂' : '未知';
}
