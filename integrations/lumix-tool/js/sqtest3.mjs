import fs from 'fs';
import zlib from 'zlib';

const img = fs.readFileSync('out/rootfs.squashfs');
const it = 0x958626;
const hdr = img.readUInt16LE(it);
const size = hdr & 0x7fff;
const payload = img.subarray(it + 2, it + 2 + size);
console.log('hdr=0x%s size=%d', hdr.toString(16), size);

function tryIt(name, fn) {
  try {
    const out = fn();
    const t = out.readUInt16LE ? out.readUInt16LE(0) : Buffer.from(out).readUInt16LE(0);
    console.log('%s -> %d bytes first16=%s type=%d',
      name, out.length, Buffer.from(out).subarray(0, 16).toString('hex'), t);
  } catch (e) {
    console.log('%s failed: %s', name, e.message);
  }
}

tryIt('inflateRaw', () => zlib.inflateRawSync(payload));
tryIt('inflate', () => zlib.inflateSync(payload));
tryIt('inflateRaw(+2)', () => zlib.inflateRawSync(img.subarray(it + 4, it + 4 + size)));

// also test the data-block area at a known file offset with raw zlib
console.log('bytes at 0x958626:', img.subarray(0x958626, 0x958626 + 16).toString('hex'));
