import fs from 'fs';
import { lzo1xDecompress } from 'lzo1x';

const img = fs.readFileSync('out/rootfs.squashfs');
// data blocks normally start right after the 96-byte superblock
for (const [start, len, exp] of [
  [0x60, 0x4000, 0x20000],
  [0x60, 0x2000, 0x20000],
  [0x60, 0x8000, 0x20000],
  [0x60, 0x1000, 0x20000],
]) {
  try {
    const out = lzo1xDecompress(img.subarray(start, start + len), exp);
    console.log('data block start=0x%s len=0x%s -> %d bytes, first32=%s',
      start.toString(16), len.toString(16), out.length, Buffer.from(out).subarray(0, 32).toString('hex'));
  } catch (e) {
    console.log('start=0x%s len=0x%s failed: %s', start.toString(16), len.toString(16), e.message);
  }
}
