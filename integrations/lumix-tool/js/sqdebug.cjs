const fs = require('fs');
const { lzo1xDecompress } = require('lzo1x');

const b = fs.readFileSync(process.argv[2] || 'out/rootfs1.squashfs');
const u64 = (p) => Number(b.readBigUInt64LE(p));
const sb = {
  blockSize: b.readUInt32LE(12), rootInode: u64(32), inodeTable: u64(64),
  dirTable: u64(72), fragTable: u64(80), exportTable: u64(88),
};
console.log(sb);

class Meta {
  constructor(start, end) {
    this.index = []; this.chunks = []; this.len = 0;
    let pos = start;
    while (pos < end) {
      const hdr = b.readUInt16LE(pos), size = hdr & 0x7fff, compressed = (hdr & 0x8000) === 0;
      const raw = b.subarray(pos + 2, pos + 2 + size);
      const data = compressed ? Buffer.from(lzo1xDecompress(raw)) : raw;
      console.log('  block hdr@0x%s size=%d comp=%s -> %d', (pos - start).toString(16), size, compressed, data.length);
      this.index.push([pos - start, this.len]);
      this.chunks.push(data); this.len += data.length;
      pos += 2 + size;
    }
    this.data = Buffer.concat(this.chunks);
  }
  read(blockOff, offset, len) {
    for (const [h, dp] of this.index) if (h === blockOff) return this.data.subarray(dp + offset, dp + offset + len);
    throw new Error('block 0x' + blockOff.toString(16) + ' missing');
  }
}

const im = new Meta(sb.inodeTable, sb.dirTable);
const dm = new Meta(sb.dirTable, sb.fragTable);

const ref = sb.rootInode;
const block = Math.floor(ref / 0x10000), off = ref % 0x10000;
console.log('root ref block=0x%s off=0x%s', block.toString(16), off.toString(16));
const d = im.read(block, off, 64);
console.log('root inode bytes:', d.toString('hex'));
console.log('type=%d mode=0o%s start=0x%s nlink=%d size=%d offset=%d parent=%d',
  d.readUInt16LE(0), d.readUInt16LE(2).toString(8), d.readUInt32LE(16).toString(16),
  d.readUInt32LE(20), d.readUInt16LE(24), d.readUInt16LE(26), d.readUInt32LE(28));

const dirData = dm.read(d.readUInt32LE(16), d.readUInt16LE(26), 256);
console.log('dir data head:', dirData.subarray(0, 96).toString('hex'));
console.log('count=%d startBlock=0x%s baseIno=%d', dirData.readUInt32LE(0), dirData.readUInt32LE(4).toString(16), dirData.readUInt32LE(8));
console.log('entry: offset=0x%s delta=%d type=%d size=%d name=%s',
  dirData.readUInt16LE(12).toString(16), dirData.readInt16LE(14), dirData.readUInt16LE(16), dirData.readUInt16LE(18),
  dirData.subarray(20, 20 + dirData.readUInt16LE(18) + 1).toString('latin1'));
