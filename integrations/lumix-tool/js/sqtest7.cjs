// Try FFmpeg's LZO on the squashfs metadata block and a data block.
const fs = require('fs');
const lzo = require('lzo-decompress');

const img = fs.readFileSync('out/rootfs.squashfs');
const it = 0x958626;
const hdr = img.readUInt16LE(it);
const size = hdr & 0x7fff;
console.log('header 0x%s size=%d', hdr.toString(16), size);

function attempt(label, start, inLen, outLen) {
  try {
    const out = lzo.decompress(img.subarray(start, start + inLen), outLen);
    const buf = Buffer.from(out);
    console.log('%s -> %d bytes first32=%s', label, buf.length, buf.subarray(0, 32).toString('hex'));
  } catch (e) {
    console.log('%s failed: %s', label, e.message);
  }
}

attempt('meta it+2', it + 2, size, 8192);
attempt('meta it+2 big-in', it + 2, 0x4000, 8192);
attempt('data 0x60 128k-in', 0x60, 0x20000, 0x20000);
attempt('data 0x60 64k-in', 0x60, 0x10000, 0x20000);
