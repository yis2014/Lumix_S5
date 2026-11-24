// Locate the fragment table by scanning backwards from frag_table_start and
// extract a small file end-to-end.
const fs = require('fs');
const { lzo1xDecompress } = require('lzo1x');

const img = fs.readFileSync(process.argv[2] || 'out/rootfs1.squashfs');
const u64 = (p) => Number(img.readBigUInt64LE(p));
const sb = {
  inodes: img.readUInt32LE(4), blockSize: img.readUInt32LE(12), frags: img.readUInt32LE(16),
  rootInode: u64(32), bytesUsed: u64(40), inodeTable: u64(64),
  dirTable: u64(72), fragTable: u64(80), lookupTable: u64(88),
};

class Meta {
  constructor(start, end) {
    this.index = []; this.chunks = []; this.len = 0;
    let pos = start;
    while (pos < end) {
      const hdr = img.readUInt16LE(pos), size = hdr & 0x7fff, comp = (hdr & 0x8000) === 0;
      const raw = img.subarray(pos + 2, pos + 2 + size);
      const data = comp ? Buffer.from(lzo1xDecompress(raw)) : raw;
      this.index.push([pos - start, this.len]);
      this.chunks.push(data); this.len += data.length;
      pos += 2 + size;
    }
    this.data = Buffer.concat(this.chunks);
  }
  read(bo, off, len) {
    for (const [h, dp] of this.index) if (h === bo) return this.data.subarray(dp + off, dp + off + len);
    throw new Error('meta block 0x' + bo.toString(16));
  }
}

const im = new Meta(sb.inodeTable, sb.dirTable);
const dm = new Meta(sb.dirTable, <FRAG_OR_END>);
// placeholder replaced below
