// Scan the data area for LZO-compressed fragment blocks and dump those that decode.
const fs = require('fs');
const { lzo1xDecompress } = require('lzo1x');

const img = fs.readFileSync(process.argv[2]);
const inodeTable = Number(process.argv[3]);
const outPrefix = process.argv[4] || 'out/frag';
const BLOCK = 0x20000;

let found = 0;
const hits = [];
for (let off = 0x60; off + 1024 < inodeTable; off += 4096) {
  const slice = img.subarray(off, off + BLOCK);
  try {
    const out = Buffer.from(lzo1xDecompress(slice, BLOCK));
    if (out.length === BLOCK) {
      const ascii = out.subarray(0, 200).toString('latin1');
      const printable = [...out.subarray(0, 4096)].filter(b => b === 9 || b === 10 || (b >= 32 && b < 127)).length;
      hits.push({ off, out, printable });
      if (printable > 3000) {
        fs.writeFileSync(`${outPrefix}_${off.toString(16)}.bin`, out);
        found++;
      }
    }
  } catch (e) { /* not a block start */ }
}
console.log('LZO blocks decoded:', hits.length, 'textual dumped:', found);
for (const h of hits.slice(0, 12)) {
  console.log('  block@0x%s printable=%d head=%s', h.off.toString(16), h.printable,
    h.out.subarray(0, 40).toString('latin1').replace(/[^ -~]/g, '.'));
}
