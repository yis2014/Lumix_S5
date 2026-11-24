import fs from 'fs';
import { lzo1xDecompress } from 'lzo1x';

const img = fs.readFileSync('out/rootfs.squashfs');
const it = 0x958626;
const hdr = img.readUInt16LE(it);
const size = hdr & 0x7fff;
const payload = img.subarray(it + 2, it + 2 + size);
console.log('hdr=0x%s size=%d flag=%d', hdr.toString(16), size, hdr >> 15);

for (const expected of [8192, 4096, 2048]) {
  try {
    const out = Buffer.from(lzo1xDecompress(payload, expected));
    const t = out.readUInt16LE(0);
    console.log('lzo(%d) -> %d bytes, first16=%s type=%d', expected, out.length, out.subarray(0, 16).toString('hex'), t);
  } catch (e) {
    console.log('lzo(%d) failed: %s', expected, e.message);
  }
}
// also try treating the whole thing as raw and look for a plausible inode later
console.log('raw first32', payload.subarray(0, 32).toString('hex'));
