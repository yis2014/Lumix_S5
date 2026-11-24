// Scan a Thumb region for instructions mentioning an immediate value.
// usage: node js/scan_imm.js <input.bin> <base-hex> <imm-hex> [limit]
const fs = require('fs');
const MCapstone = require('@alexaltea/capstone-js');

const [input, baseStr, immStr, limitStr] = process.argv.slice(2);
const base = parseInt(baseStr, 16);
const imm = BigInt('0x' + immStr);
const limit = parseInt(limitStr || '200', 10);
const buf = fs.readFileSync(input);

MCapstone().then((cs) => {
  const d = new cs.Capstone(cs.ARCH_ARM, cs.MODE_THUMB);
  const hits = [];
  let off = 0;
  let n = 0;
  while (off < buf.length && hits.length < limit) {
    let decoded = null;
    try { decoded = d.disasm(buf.subarray(off), base + off); } catch (e) { decoded = null; }
    if (decoded && decoded.length > 0) {
      for (const ins of decoded) {
        n++;
        const addr = Number(ins.address);
        if (addr >= base + buf.length) break;
        const txt = (ins.mnemonic + ' ' + ins.op_str).toLowerCase();
        if (txt.includes('0x' + imm.toString(16))) {
          hits.push(`${addr.toString(16)}: ${ins.mnemonic} ${ins.op_str}`);
        }
      }
      const last = decoded[decoded.length - 1];
      const next = (Number(last.address) - base) + last.size;
      if (next <= off) break;
      off = next;
    } else {
      off += 2;
    }
  }
  console.log(`scanned ${n} instructions, hits=${hits.length}`);
  for (const h of hits) console.log('  ' + h);
});
