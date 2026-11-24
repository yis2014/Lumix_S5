import fs from 'fs';
import { lzo1xDecompress } from 'lzo1x';

const img = fs.readFileSync('out/rootfs.squashfs');
const it = 0x958626;
for (let delta = 0; delta <= 16; delta++) {
  try {
    const out = Buffer.from(lzo1xDecompress(img.subarray(it + delta, it + delta + 0x4000)));
    const t = out.readUInt16LE(0);
    console.log('delta=%d -> %d bytes type=%d first32=%s', delta, out.length, t, out.subarray(0, 32).toString('hex'));
  } catch (e) { /* next */ }
}
// also try the directory table start
const dt = 0x95BEF2;
for (let delta = 0; delta <= 4; delta++) {
  try {
    const out = Buffer.from(lzo1xDecompress(img.subarray(dt + delta, dt + delta + 0x4000)));
    console.log('dir delta=%d -> %d bytes first32=%s', delta, out.length, out.subarray(0, 32).toString('hex'));
  } catch (e) { /* next */ }
}
console.log('done');
