// Brute-force PC-relative reference finder (no 32-bit bitwise ops on addresses).
// usage: node js/find_pcrel2.js <input.bin> <base-hex> <target-hex>
const fs = require('fs');
const MCapstone = require('@alexaltea/capstone-js');
const [input, baseStr, targetStr] = process.argv.slice(2);
const base = parseInt(baseStr, 16);
const target = parseInt(targetStr, 16);
const buf = fs.readFileSync(input);
const align4 = v => v - (v % 4);
MCapstone().then((cs) => {
  const d = new cs.Capstone(cs.ARCH_ARM, cs.MODE_THUMB);
  const re = /(addw|subw|add|sub)\.?w?\s+r\d+,\s*pc,\s*#(-?0x[0-9a-f]+)/i;
  let hits = 0;
  for (let off = 0; off + 4 <= buf.length; off += 2) {
    let dec = null;
    try { dec = d.disasm(buf.subarray(off, off + 4), base + off); } catch (e) { continue; }
    if (!dec || !dec.length) continue;
    const ins = dec[0];
    if (ins.size !== 4) continue;
    const m = re.exec(ins.mnemonic + ' ' + ins.op_str);
    if (!m) continue;
    const imm = parseInt(m[2], 16);
    const pc = align4(base + off + 4);
    const t = m[1].toLowerCase().startsWith('sub') ? pc - imm : pc + imm;
    if (t === target) {
      hits++;
      console.log('0x' + (base + off).toString(16) + ': ' + ins.mnemonic + ' ' + ins.op_str);
    }
  }
  console.log('hits:', hits);
});
