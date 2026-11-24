// Try LZ4 on the squashfs metadata and data blocks.
const fs = require('fs');
const lz4 = require('lz4js');

const img = fs.readFileSync('out/rootfs.squashfs');
const it = 0x958626;
const hdr = img.readUInt16LE(it);
const size = hdr & 0x7fff;
console.log('header 0x%s size=%d', hdr.toString(16), size);

function attempt(label, start, inLen, outLen) {
  try {
    const out = lz4.decompress(img.subarray(start, start + inLen), outLen);
    const buf = Buffer.from(out);
    console.log('%s -> %d bytes first32=%s type=%d', label, buf.length, buf.subarray(0, 32).toString('hex'), buf.readUInt16LE(0));
  } catch (e) {
    console.log('%s failed: %s', label, e.message);
  }
}

attempt('meta it+2 (2698 in, 8192 out)', it + 2, size, 8192);
attempt('meta it+2 (16k in)', it + 2, 0x4000, 8192);
attempt('meta it+2 (8k in)', it + 2, 0x2000, 8192);
attempt('data 0x60 (64k in, 128k out)', 0x60, 0x10000, 0x20000);
attempt('data 0x60 (128k in, 128k out)', 0x60, 0x20000, 0x20000);
attempt('data 0x60 (32k in, 128k out)', 0x60, 0x8000, 0x20000);
