const fs = require('fs');
const { lzo1xDecompress } = require('lzo1x');
const b = fs.readFileSync(process.argv[2] || 'out/rootfs1.squashfs');
const u64 = (p) => Number(b.readBigUInt64LE(p));
const sb = {
  blockSize: b.readUInt32LE(12), rootInode: u64(32), inodeTable: u64(64),
  dirTable: u64(72), fragTable: u64(80), exportTable: u64(88), idTable: u64(48),
};
class Meta {
  constructor(start, end) {
    this.index = []; this.chunks = []; this.len = 0;
    let pos = start;
    while (pos < end) {
      const hdr = b.readUInt16LE(pos), size = hdr & 0x7fff, comp = (hdr & 0x8000) === 0;
      const raw = b.subarray(pos + 2, pos + 2 + size);
      const data = comp ? Buffer.from(lzo1xDecompress(raw)) : raw;
      this.index.push([pos - start, this.len]);
      this.chunks.push(data); this.len += data.length;
      pos += 2 + size;
    }
    this.data = Buffer.concat(this.chunks);
  }
  read(bo, off, len) {
    for (const [h, dp] of this.index) if (h === bo) return this.data.subarray(dp + off, dp + off + len);
    throw new Error('missing block 0x' + bo.toString(16));
  }
}
const im = new Meta(sb.inodeTable, sb.dirTable);
const dm = new Meta(sb.dirTable, sb.fragTable);
const fm = new Meta(sb.fragTable, sb.exportTable);
console.log('frag table bytes:', fm.len, 'entries:', fm.len / 16);
for (let i = 0; i < Math.min(5, fm.len / 16); i++) {
  const p = i * 16;
  console.log('frag %d start=0x%s size=0x%s unused=%d', i,
    fm.data.readBigUInt64LE(p).toString(16), fm.data.readUInt32LE(p + 8).toString(16), fm.data.readUInt32LE(p + 12));
}
// find /etc/fstab
function findInode(node, want) {
  if (node.type !== 1) return null;
  const d = dm.read(node.start, node.offset, node.size);
  let p = 0;
  while (p + 12 <= d.length) {
    const count = d.readUInt32LE(p), startBlock = d.readUInt32LE(p + 4), baseIno = d.readUInt32LE(p + 8);
    p += 12;
    for (let i = 0; i < count + 1; i++) {
      const off = d.readUInt16LE(p), size = d.readUInt16LE(p + 6);
      p += 8;
      const name = d.subarray(p, p + size + 1).toString('latin1').replace(/\0.*$/, '');
      p += size + 1;
      const ref = (startBlock << 16) | off;
      if (name === want) return ref;
      if (name) { /* continue */ }
    }
  }
  return null;
}
const root = sb.rootInode;
const rootNode = (() => { const bl = Math.floor(root / 0x10000), of = root % 0x10000; const d = im.read(bl, of, 64);
  return { type: d.readUInt16LE(0), start: d.readUInt32LE(16), offset: d.readUInt16LE(26), size: d.readUInt16LE(24) }; })();
const fstab = findInode(rootNode, 'fstab');
console.log('fstab ref 0x' + fstab.toString(16));
const bl = Math.floor(fstab / 0x10000), of = fstab % 0x10000;
const d = im.read(bl, of, 64);
console.log('inode type=%d size=%d start=0x%s frag=%d off=%d', d.readUInt16LE(0), d.readUInt32LE(28), d.readUInt32LE(16).toString(16), d.readUInt32LE(20), d.readUInt32LE(24));
const frag = d.readUInt32LE(20);
if (frag !== 0xffffffff) {
  const p = frag * 16;
  const start = Number(fm.data.readBigUInt64LE(p)), size = fm.data.readUInt32LE(p + 8);
  console.log('fragment %d: start=0x%s size=0x%s flag=%d', frag, start.toString(16), (size & 0xffffff).toString(16), size >> 24);
  const raw = b.subarray(start, start + (size & 0xffffff));
  console.log('frag bytes:', raw.subarray(0, 16).toString('hex'));
  try { const out = Buffer.from(lzo1xDecompress(raw)); console.log('dyn ->', out.length); } catch (e) { console.log('dyn fail', e.message); }
  try { const out = Buffer.from(lzo1xDecompress(raw, sb.blockSize)); console.log('blockSize ->', out.length); } catch (e) { console.log('blockSize fail', e.message); }
}
