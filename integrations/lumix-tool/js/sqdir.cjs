const fs = require('fs');
const { lzo1xDecompress } = require('lzo1x');

for (const [name, path, off] of [
  ['rootfs1', 'out/rootfs1.squashfs', 0x26AF2C],
  ['rootfs2', 'out/rootfs2.squashfs', 0x95E23C],
]) {
  const b = fs.readFileSync(path);
  const hdr = b.readUInt16LE(off);
  const size = hdr & 0x7fff;
  const payload = b.subarray(off + 2, off + 2 + size);
  console.log('%s: header=0x%s size=%d', name, hdr.toString(16), size);
  for (const mode of ['dyn', 8192, 4096, 1024, 512, 256]) {
    try {
      const out = mode === 'dyn'
        ? Buffer.from(lzo1xDecompress(payload))
        : Buffer.from(lzo1xDecompress(payload, mode));
      console.log('  %s -> %d bytes first32=%s', mode, out.length, out.subarray(0, 32).toString('hex'));
      break;
    } catch (e) {
      console.log('  %s failed: %s', mode, e.message);
    }
  }
}
