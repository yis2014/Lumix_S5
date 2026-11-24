// Sequential Thumb/ARM disassembler with recovery, for mixed code/data blobs.
// usage: node js/disasm_linear.js <input.bin> <base-hex> <out.txt> [thumb|arm]
const fs = require('fs');
const MCapstone = require('@alexaltea/capstone-js');

const [input, baseStr, outPath, modeArg] = process.argv.slice(2);
const base = parseInt(baseStr, 16);
const buf = fs.readFileSync(input);
const mode = (modeArg || 'thumb').toLowerCase();

MCapstone().then((cs) => {
  const mdMode = mode === 'thumb' ? cs.MODE_THUMB : cs.MODE_ARM;
  const d = new cs.Capstone(cs.ARCH_ARM, mdMode);
  const lines = [];
  let off = 0;
  let good = 0, bad = 0;
  while (off + 2 <= buf.length) {
    let decoded = null;
    try {
      decoded = d.disasm(buf.subarray(off), base + off);
    } catch (e) {
      decoded = null;
    }
    if (decoded && decoded.length > 0) {
      for (const ins of decoded) {
        const addr = Number(ins.address);
        if (addr >= base + buf.length) break;
        const b = buf.subarray(addr - base, addr - base + ins.size);
        lines.push(
          `${addr.toString(16).padStart(8, '0')}  ${b.toString('hex').padEnd(8)}  ${ins.mnemonic}\t${ins.op_str}`
        );
        good++;
      }
      const last = decoded[decoded.length - 1];
      const next = (Number(last.address) - base) + last.size;
      if (next <= off) break;
      off = next;
    } else {
      const w = buf.readUInt16LE(off);
      lines.push(`${(base + off).toString(16).padStart(8, '0')}  ${w.toString(16).padStart(4, '0')}      .hword\t0x${w.toString(16)}`);
      bad++;
      off += 2;
    }
  }
  fs.writeFileSync(outPath, lines.join('\n') + '\n');
  console.log(`instructions=${good} data_or_unknown=${bad} -> ${outPath}`);
});

