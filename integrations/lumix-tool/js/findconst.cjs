// Disassemble a range of the main-core dump as Thumb and report instructions
// whose operands mention interesting constants.
const fs = require('fs');
const MCapstone = require('@alexaltea/capstone-js');

const BIN = 'ref/program_0x86280000.bin';
const BASE = 0x86280000;
const start = parseInt(process.argv[2] || '0x86280000', 16);
const end = parseInt(process.argv[3] || '0x86480000', 16);
const targets = (process.argv[4] || 'dc00000,df00000').split(',');

const buf = fs.readFileSync(BIN);
const from = start - BASE;
const to = Math.min(buf.length, end - BASE);

MCapstone().then((cs) => {
  const d = new cs.Capstone(cs.ARCH_ARM, cs.MODE_THUMB);
  const hits = [];
  let off = from;
  let n = 0;
  const t0 = Date.now();
  while (off + 4 <= to) {
    const chunk = buf.subarray(off, off + 4);
    let ins = null;
    try { ins = d.disasm(chunk, BASE + off); } catch (e) { ins = null; }
    if (ins && ins.length) {
      const s = (ins[0].mnemonic + ' ' + ins[0].op_str).toLowerCase();
      for (const t of targets) {
        if (s.includes('0x' + t)) {
          hits.push(`${(BASE + off).toString(16)}  ${ins[0].mnemonic}\t${ins[0].op_str}`);
        }
      }
      off += ins[0].size;
      n++;
    } else {
      off += 2;
    }
  }
  console.log('disassembled', n, 'instrs in', ((Date.now() - t0) / 1000).toFixed(1), 's');
  console.log('hits:', hits.length);
  for (const h of hits.slice(0, 60)) console.log('  ' + h);
  d.close();
}).catch((e) => { console.error(e); process.exit(1); });
