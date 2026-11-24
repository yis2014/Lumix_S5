// rootfs fragment fix: the fragment table metadata block is the block pointed
// to by the u64 stored at fragment_table_start (that slot is a lookup table).
// Then extract /etc/fstab end-to-end as a proof.
const fs = require('fs');
const { lzo1xDecompress } = require('lzo1x');

const img = fs.readFileSync(process.argv[2] || 'out/rootfs1.squashfs');
const u64 = (p) => Number(img.readBigUInt64LE(p));
const sb = {
  blockSize: img.readUInt32LE(12), frags: img.readUInt32LE(16),
  rootInode: u64(32), bytesUsed: u64(40), inodeTable: u64(64),
  dirTable: u64(72), fragTable: u64(80), lookupTable: u64(88),
};
console.log('root=%s inode_tab=0x%s dir_tab=0x%s frag_tab=0x%s lookup=0x%s frags=%d',
  '0x' + sb.rootInode.toString(16), sb.inodeTable.toString(16), sb.dirTable.toString(16),
  sb.fragTable.toString(16), sb.lookupTable.toString(16), sb.frags);

const fragBlockOff = u64(sb.fragTable);
console.log('fragment metadata block at 0x%s', fragBlockOff.toString(16));
const fragHdr = img.readUInt16LE(fragBlockOff);
const fragSize = fragHdr & 0x7fff;
const fragComp = (fragHdr & 0x8000) === 0;
const fragRaw = img.subarray(fragBlockOff + 2, fragBlockOff + 2 + fragSize);
const fragData = fragComp ? Buffer.from(lzo1xDecompress(fragRaw)) : fragRaw;
console.log('frag table: hdr=0x%s size=%d comp=%s -> %d bytes = %d entries',
  fragHdr.toString(16), fragSize, fragComp, fragData.length, fragData.length / 16);

function fragEntry(i) {
  const p = i * 16;
  return { start: Number(fragData.readBigUInt64LE(p)), size: fragData.readUInt32LE(p + 8) };
}
for (let i = 0; i < Math.min(3, sb.frags); i++) {
  const e = fragEntry(i);
  console.log('  frag %d start=0x%s size=0x%s', i, e.start.toString(16), (e.size & 0xffffff).toString(16));
}

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
const dm = new Meta(sb.dirTable, fragBlockOff);

function parseInode(ref) {
  const bl = Math.floor(ref / 0x10000), of = ref % 0x10000;
  const d = im.read(bl, of, 512);
  const type = d.readUInt16LE(0);
  const n = { type };
  let p = 16;
  if (type === 1) {
    n.start = d.readUInt32LE(p); n.size = d.readUInt16LE(p + 8); n.offset = d.readUInt16LE(p + 10);
  } else if (type === 2) {
    n.start = d.readUInt32LE(p); n.frag = d.readUInt32LE(p + 4);
    n.offset = d.readUInt32LE(p + 8); n.size = d.readUInt32LE(p + 12);
    p += 16;
    let nb = Math.ceil(n.size / sb.blockSize);
    if (n.frag !== 0xffffffff) nb = Math.floor(n.size / sb.blockSize);
    n.blocks = [];
    for (let i = 0; i < nb; i++) { n.blocks.push(d.readUInt32LE(p)); p += 4; }
  } else if (type === 3) {
    n.size = d.readUInt32LE(p + 4); n.target = d.subarray(p + 8, p + 8 + n.size).toString('latin1');
  }
  return n;
}

function dirEntries(node) {
  const d = dm.read(node.start, node.offset, node.size);
  const out = []; let p = 0;
  const s16 = (v) => (v & 0x8000) ? v - 0x10000 : v;
  while (p + 12 <= d.length) {
    const count = d.readUInt32LE(p), sbk = d.readUInt32LE(p + 4), base = d.readUInt32LE(p + 8);
    p += 12;
    for (let i = 0; i < count + 1 && p + 8 <= d.length; i++) {
      const off = d.readUInt16LE(p), delta = s16(d.readUInt16LE(p + 2)), size = d.readUInt16LE(p + 6);
      p += 8;
      const name = d.subarray(p, p + size + 1).toString('latin1').replace(/\0.*$/, '');
      p += size + 1;
      if (!name) return out;
      out.push({ name, ino: base + delta, ref: (sbk << 16) | off });
    }
  }
  return out;
}

function lookup(pathParts) {
  let node = parseInode(sb.rootInode);
  for (const part of pathParts) {
    const e = dirEntries(node).find(x => x.name === part);
    if (!e) throw new Error('not found: ' + part);
    node = parseInode(e.ref);
  }
  return node;
}

function readFile(n) {
  const parts = [];
  let remaining = n.size;
  let start = n.start;
  for (const ent of n.blocks) {
    const comp = (ent & 0x1000000) === 0, len = ent & 0xffffff;
    const raw = img.subarray(start, start + len);
    const take = Math.min(remaining, sb.blockSize);
    parts.push(comp ? Buffer.from(lzo1xDecompress(raw)).subarray(0, take) : raw.subarray(0, take));
    start += len; remaining -= take;
  }
  if (n.frag !== 0xffffffff && remaining > 0) {
    const fe = fragEntry(n.frag);
    const comp = (fe.size & 0x1000000) === 0, len = fe.size & 0xffffff;
    const raw = img.subarray(fe.start, fe.start + len);
    const full = comp ? Buffer.from(lzo1xDecompress(raw)) : raw;
    parts.push(full.subarray(n.offset, n.offset + remaining));
  }
  return Buffer.concat(parts);
}

for (const p of [['etc', 'fstab'], ['etc', 'inittab'], ['etc', 'init.d', 'rcS']]) {
  try {
    const n = lookup(p);
    const data = readFile(n);
    console.log('\n=== /%s (%d bytes) ===', p.join('/'), data.length);
    console.log(data.subarray(0, 400).toString('latin1'));
  } catch (e) {
    console.log('\n/%s -> ERROR %s', p.join('/'), e.message);
  }
}

