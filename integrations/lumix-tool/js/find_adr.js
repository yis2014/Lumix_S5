// Find Thumb ADR instructions whose target equals a given address.
// usage: node js/find_adr.js <input.bin> <base-hex> <target-hex>
const fs = require('fs');
const MCapstone = require('@alexaltea/capstone-js');

const [input, baseStr, targetStr] = process.argv.slice(2);
const base = parseInt(baseStr, 16);
const target = parseInt(targetStr, 16);
const buf = fs.readFileSync(input);

MCapstone().then((cs) => {
  const d = new cs.Capstone(cs.ARCH_ARM, cs.MODE_THUMB);
  let off = 0;
  let hits = 0;
  while (off < buf.length) {
    let decoded = null;
    try { decoded = d.disasm(buf.subarray(off), base + off); } catch (e) { decoded = null; }
    if (decoded && decoded.length > 0) {
      for (const ins of decoded) {
        const addr = Number(ins.address);
        if (addr >= base + buf.length) break;
        if (ins.mnemonic === 'adr') {
          const m = /#(-?0x[0-9a-f]+)/i.exec(ins.op_str);
          if (m) {
            const imm = parseInt(m[1], 16);
            const pc = (addr + 4) & ~3;
            const t = pc + imm;
            if (t === target) {
              hits++;
              console.log('ADR at 0x' + addr.toString(16) + ': ' + ins.mnemonic + ' ' + ins.op_str);
            }
          }
        }
      }
      const last = decoded[decoded.length - 1];
      const next = (Number(last.address) - base) + last.size;
      if (next <= off) break;
      off = next;
    } else off += 2;
  }
  console.log('hits:', hits);
});
