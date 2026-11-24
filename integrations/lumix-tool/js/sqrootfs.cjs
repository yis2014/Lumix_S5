// Try LZO on the rootfs1 (slram0) and rootfs2 (slram1) metadata blocks.
const fs = require('fs');
const zlib = require('zlib');
const lzoTs = require('lzo1x');

const img = fs.readFileSync('out/ram_rootfs.bin');
const BASE = 0x83000000;

function carve(addr, size, out) {
  const off = addr - BASE;
  fs.writeFileSync(out, img.subarray(off, off + size));
}

// superblock parse
function sb(addr) {
  const o = addr - BASE;
  const u32 = (p) => img.readUInt32LE(o + p);
  const u16 = (p) => img.readUInt16LE(o + p);
  const u64 = (p) => Number(img.readBigUInt64LE(o + p));
  return {
    inodes: u32(4), blockSize: u32(12), comp: u16(20),
    bytesUsed: u64(40), inodeTable: u64(64), dirTable: u64(72),
  };
}

for (const [name, addr] of [['rootfs1', 0x83100000], ['rootfs2', 0x83400000]]) {
  const s = sb(addr);
  console.log('\n%s: inodes=%d comp=%d used=0x%s inodeTable=0x%s',
    name, s.inodes, s.comp, s.bytesUsed.toString(16), s.inodeTable.toString(16));
  carve(addr, s.bytesUsed, `out/${name}.squashfs`);
  const off = addr - BASE + s.inodeTable;
  const hdr = img.readUInt16LE(off);
  const size = hdr & 0x7fff;
  console.log('  metadata header 0x%s size=%d flag=%d', hdr.toString(16), size, hdr >> 15);
  const payload = img.subarray(off + 2, off + 2 + size);
  for (const [label, fn] of [
    ['lzo-ts 8192', () => Buffer.from(lzoTs.lzo1xDecompress(payload, 8192))],
    ['inflateRaw', () => zlib.inflateRawSync(payload)],
  ]) {
    try {
      const out = fn();
      console.log('  %s -> %d bytes first16=%s type=%d', label, out.length,
        out.subarray(0, 16).toString('hex'), out.readUInt16LE(0));
    } catch (e) {
      console.log('  %s failed: %s', label, e.message);
    }
  }
}
