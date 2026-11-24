// Disassemble a raw ARM32 blob with capstone.js, tolerating data gaps.
// usage: node js/disasm.js <input.bin> <base-addr-hex> <out.txt> [arm|thumb]
const fs = require('fs');
const MCapstone = require('@alexaltea/capstone-js');

const [input, baseStr, outPath, modeArg] = process.argv.slice(2);
const base = parseInt(baseStr, 16);
const buf = fs.readFileSync(input);
const mode = (modeArg || 'arm').toLowerCase();

MCapstone().then((cs) => {
  const md = mode === 'thumb' ? cs.MODE_THUMB : cs.MODE_ARM;
  const d = new cs.Capstone(cs.ARCH_ARM, md);
  const lines = [];
  let good = 0, bad = 0;
  let off = 0;
  while (off + 4 <= buf.length) {
    const chunk = buf.subarray(off, off + 4);
    let ins = null;
    try { ins = d.disasm(chunk, base + off); } catch (e) { ins = null; }
    if (ins && ins.length === 1) {
      const i = ins[0];
      const bytes = Array.from(chunk).map(b => b.toString(16).padStart(2, '0')).join(' ');
      lines.push(`${i.address.toString(16).padStart(8, '0')}  ${bytes.padEnd(12)}  ${i.mnemonic}\t${i.op_str}`);
      good++;
    } else {
      const w = chunk.readUInt32LE(0);
      lines.push(`${(base + off).toString(16).padStart(8, '0')}  ${chunk.toString('hex')}    .word\t0x${w.toString(16)}`);
      bad++;
    }
    off += 4;
  }
  fs.writeFileSync(outPath, lines.join('\n'));
  console.log(`instructions=${good} data_or_unknown=${bad} -> ${outPath}`);
  d.close();
}).catch((e) => { console.error(e); process.exit(1); });
