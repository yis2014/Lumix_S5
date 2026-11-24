// Find Thumb PC-relative ADDW/SUBW references:  addw/subw rX, pc, #imm
// usage: node js/find_pcrel.js <input.bin> <base-hex> <target-hex>
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
        const m = /(addw|subw|add|sub)\.?w?\s+r\d+,\s*pc,\s*#(-?0x[0-9a-f]+)/i.exec(ins.mnemonic + ' ' + ins.op_str);
        if (m) {
          const imm = parseInt(m[2], 16);
          const pc = (addr + 4) & ~3;
          const t = m[1].toLowerCase().startsWith('sub') ? pc - imm : pc + imm;
          if (t === target) {
            hits++;
            console.log('0x' + addr.toString(16) + ': ' + ins.mnemonic + ' ' + ins.op_str);
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
