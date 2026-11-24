// Disassemble a window of the main-core dump around an address.
// usage: node js/diswin.cjs <addr-hex> <before-bytes> <after-bytes> <arm|thumb> [outfile]
const fs = require('fs');
const MCapstone = require('@alexaltea/capstone-js');

const BIN = 'ref/program_0x86280000.bin';
const BASE = 0x86280000;
const [addrStr, beforeStr, afterStr, modeArg, outPath] = process.argv.slice(2);
const addr = parseInt(addrStr, 16);
const before = parseInt(beforeStr, 0);
const after = parseInt(afterStr, 0);
const mode = (modeArg || 'thumb').toLowerCase();
const buf = fs.readFileSync(BIN);

const start = Math.max(0, addr - BASE - before);
const end = Math.min(buf.length, addr - BASE + after);
const slice = buf.subarray(start, end);

MCapstone().then((cs) => {
  const md = mode === 'arm' ? cs.MODE_ARM : cs.MODE_THUMB;
  const d = new cs.Capstone(cs.ARCH_ARM, md);
  const lines = [];
  let off = 0;
  const step = mode === 'arm' ? 4 : 2;
  while (off + step <= slice.length) {
    const chunk = slice.subarray(off, off + step);
    let ins = null;
    try { ins = d.disasm(chunk, BASE + start + off); } catch (e) { ins = null; }
    const a = BASE + start + off;
    if (ins && ins.length >= 1) {
      const i = ins[0];
      const bytes = Array.from(chunk).map(b => b.toString(16).padStart(2, '0')).join(' ');
      lines.push(`${a.toString(16).padStart(8, '0')}  ${bytes.padEnd(8)}  ${i.mnemonic}\t${i.op_str}`);
    } else {
      lines.push(`${a.toString(16).padStart(8, '0')}  ${Buffer.from(chunk).toString('hex').padEnd(8)}  .hword\t0x${chunk.readUInt16LE(0).toString(16)}`);
    }
    off += step;
  }
  const text = lines.join('\n');
  if (outPath) fs.writeFileSync(outPath, text);
  // print a window around the anchor
  const anchor = addr - (BASE + start);
  console.log(lines.filter(l => {
    const v = parseInt(l.slice(0, 8), 16);
    return v >= addr - 0x60 && v <= addr + 0xa0;
  }).join('\n'));
  console.log('--- total lines', lines.length, outPath ? '-> ' + outPath : '');
  d.close();
}).catch((e) => { console.error(e); process.exit(1); });
