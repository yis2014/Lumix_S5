// Raw LZ4 block decompression attempts on the squashfs image.
const fs = require('fs');
const lz4 = require('lz4js');

const img = fs.readFileSync('out/rootfs.squashfs');
const it = 0x958626;
const hdr = img.readUInt16LE(it);
const size = hdr & 0x7fff;
console.log('header 0x%s size=%d', hdr.toString(16), size);

function attempt(label, start, inLen, outLen) {
  try {
    const dst = Buffer.alloc(outLen);
    const n = lz4.decompressBlock(img, dst, start, inLen, 0);
    console.log('%s -> wrote %d first32=%s type=%d', label, n,
      dst.subarray(0, 32).toString('hex'), n >= 2 ? dst.readUInt16LE(0) : -1);
  } catch (e) {
    console.log('%s failed: %s', label, e.message);
  }
}

attempt('meta it+2 len=size', it + 2, size, 8192);
attempt('meta it+2 len=8192', it + 2, 8192, 8192);
attempt('meta it+2 len=4096', it + 2, 4096, 8192);
attempt('data 0x60 len=128k', 0x60, 0x20000, 0x20000);
attempt('data 0x60 len=64k', 0x60, 0x10000, 0x20000);
attempt('data 0x60 len=32k', 0x60, 0x8000, 0x20000);
