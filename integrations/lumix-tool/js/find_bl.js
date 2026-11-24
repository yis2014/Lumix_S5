// Find BL call sites to a target address and print preceding instructions.
// usage: node js/find_bl.js <input.bin> <base-hex> <target-hex> [ctx]
const fs = require('fs');
const MCapstone = require('@alexaltea/capstone-js');

const [input, baseStr, targetStr, ctxStr] = process.argv.slice(2);
const base = parseInt(baseStr, 16);
const target = parseInt(targetStr, 16);
const ctx = parseInt(ctxStr || '6', 10);
const buf = fs.readFileSync(input);

MCapstone().then((cs) => {
  const d = new cs.Capstone(cs.ARCH_ARM, cs.MODE_THUMB);
  const ring = [];
  let off = 0;
  let hits = 0;
  while (off < buf.length) {
    let decoded = null;
    try { decoded = d.disasm(buf.subarray(off), base + off); } catch (e) { decoded = null; }
    if (decoded && decoded.length > 0) {
      for (const ins of decoded) {
        const addr = Number(ins.address);
        if (addr >= base + buf.length) break;
        if (ins.mnemonic === 'bl' || ins.mnemonic === 'bl.w') {
          const t = parseInt(ins.op_str.replace('#', ''), 16);
          if (t === target) {
            hits++;
            console.log('--- call at 0x' + addr.toString(16) + ' ---');
            for (const r of ring) console.log('   ' + r);
            console.log('   ' + addr.toString(16) + ': bl ' + ins.op_str);
          }
        }
        ring.push(addr.toString(16) + ': ' + ins.mnemonic + ' ' + ins.op_str);
        if (ring.length > ctx) ring.shift();
      }
      const last = decoded[decoded.length - 1];
      const next = (Number(last.address) - base) + last.size;
      if (next <= off) break;
      off = next;
    } else {
      off += 2;
    }
  }
  console.log('total call sites:', hits);
});
