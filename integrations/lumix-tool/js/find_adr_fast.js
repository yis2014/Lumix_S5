// Fast ADR (T1) reference scanner: 10100 Rd imm8, target = Align(PC,4)+imm8*4
// usage: node js/find_adr_fast.js <input.bin> <base-hex> <target-hex> [...]
const fs = require('fs');
const input = process.argv[2];
const base = parseInt(process.argv[3], 16);
const targets = new Set(process.argv.slice(4).map(v => parseInt(v, 16)));
const buf = fs.readFileSync(input);
const align4 = v => v - (v % 4);
let hits = 0;
for (let off = 0; off + 2 <= buf.length; off += 2) {
  const hw = buf[off] | (buf[off + 1] << 8);
  if ((hw & 0xF800) !== 0xA000) continue;
  const rd = (hw >> 8) & 7;
  const imm8 = hw & 0xFF;
  const addr = base + off;
  const pc = align4(addr + 4);
  const t = pc + imm8 * 4;
  if (targets.has(t)) {
    hits++;
    console.log('0x' + addr.toString(16) + '  adr r' + rd + ', #0x' + (imm8 * 4).toString(16) +
      '  -> 0x' + t.toString(16));
  }
}
console.log('hits:', hits);
