// Scan for MOVW/MOVT (T3) instructions carrying a given 16-bit immediate.
// usage: node js/find_movwt.js <input.bin> <base-hex> <imm16-hex> [kind: movw|movt|both]
const fs = require('fs');
const input = process.argv[2];
const base = parseInt(process.argv[3], 16);
const imm = parseInt(process.argv[4], 16);
const kind = (process.argv[5] || 'both').toLowerCase();
const buf = fs.readFileSync(input);
let hits = 0;
for (let off = 0; off + 4 <= buf.length; off += 2) {
  const a = buf[off], b = buf[off + 1], c = buf[off + 2], d = buf[off + 3];
  const hw1 = a | (b << 8);
  const hw2 = c | (d << 8);
  if ((hw1 & 0xFBF0) !== 0xF240 && (hw1 & 0xFBF0) !== 0xF2C0) continue; // movw / movt
  const isMovt = (hw1 & 0x0080) !== 0;
  if (kind === 'movw' && isMovt) continue;
  if (kind === 'movt' && !isMovt) continue;
  if ((hw2 & 0x8000) !== 0) continue;
  const i = (hw1 >> 10) & 1;
  const imm4 = hw1 & 0xF;
  const imm3 = (hw2 >> 12) & 7;
  const imm8 = hw2 & 0xFF;
  const value = (imm4 << 12) | (i << 11) | (imm3 << 8) | imm8;
  if (value !== imm) continue;
  hits++;
  const rd = (hw2 >> 8) & 0xF;
  console.log('0x' + (base + off).toString(16) + '  ' + (isMovt ? 'movt' : 'movw') +
    '  r' + rd + ', #0x' + value.toString(16));
}
console.log('hits:', hits);
