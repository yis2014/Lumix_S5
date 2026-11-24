// Fast PC-relative reference scanner for Thumb-2 ADDW/SUBW rX, pc, #imm12.
// No disassembler needed: matches the instruction encoding directly, so it
// works across data/jump-table regions where linear decoding would diverge.
// usage: node js/find_pcrel_fast.js <input.bin> <base-hex> <target-hex> [target2...]
const fs = require('fs');
const input = process.argv[2];
const base = parseInt(process.argv[3], 16);
const targets = new Set(process.argv.slice(4).map(v => parseInt(v, 16)));
const buf = fs.readFileSync(input);
const align4 = v => v - (v % 4);
const ADDW_MASK = 0xFB8F;
const ADDW_VAL = 0xF20F;
const SUBW_VAL = 0xF28F;
let hits = 0;
for (let off = 0; off + 4 <= buf.length; off += 2) {
  const hw1 = buf[off] | (buf[off + 1] << 8);
  const masked = hw1 & ADDW_MASK;
  if (masked !== ADDW_VAL && masked !== SUBW_VAL) continue;
  const hw2 = buf[off + 2] | (buf[off + 3] << 8);
  if ((hw2 & 0x8000) !== 0) continue; // T4 requires bit15 = 0
  const imm12 = ((hw2 >> 12) << 8) | (hw2 & 0xFF);
  if (imm12 === 0) continue;
  const addr = base + off;
  const pc = align4(addr + 4);
  const t = masked === SUBW_VAL ? pc - imm12 : pc + imm12;
  if (targets.has(t)) {
    hits++;
    console.log('0x' + addr.toString(16) + '  ' + (masked === SUBW_VAL ? 'subw' : 'addw') +
      ' pc, #0x' + imm12.toString(16) + '  -> 0x' + t.toString(16));
  }
}
console.log('hits:', hits);
