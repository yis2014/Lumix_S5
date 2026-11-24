import fs from 'fs';
import { lzo1xDecompress } from 'lzo1x';

const img = fs.readFileSync('out/rootfs.squashfs');
const it = 0x958626;
for (let delta = 0; delta <= 8; delta++) {
  for (const take of [0x1000, 0x2000, 0x4000]) {
    try {
      const out = lzo1xDecompress(img.subarray(it + delta, it + delta + take), 8192);
      const t = Buffer.from(out).readUInt16LE(0);
      console.log('delta=%d take=0x%s -> %d bytes type=%d first32=%s',
        delta, take.toString(16), out.length, t, Buffer.from(out).subarray(0, 32).toString('hex'));
      if (t >= 1 && t <= 14) process.exit(0);
    } catch (e) { /* keep trying */ }
  }
}
console.log('no delta worked');
