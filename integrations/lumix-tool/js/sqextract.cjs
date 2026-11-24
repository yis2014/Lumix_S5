// Full squashfs 4.0 extractor for the S5 slram rootfs images.
// Metadata blocks are mostly raw; the few compressed ones decode with lzo1x.
// usage: node js/sqextract.cjs <image.squashfs> <outdir>
const fs = require('fs');
const path = require('path');
const { lzo1xDecompress } = require('lzo1x');

const [imgPath, outDir] = process.argv.slice(2);
const b = fs.readFileSync(imgPath);

function decomp(buf) {
  return Buffer.from(lzo1xDecompress(buf));
}

class Meta {
  constructor(start, end) {
    this.index = [];       // [headerOffset, dataPosition]
    this.chunks = [];
    this.len = 0;
    let pos = start;
    while (pos < end) {
      const hdr = b.readUInt16LE(pos);
      const size = hdr & 0x7fff;
      const compressed = (hdr & 0x8000) === 0;
      const raw = b.subarray(pos + 2, pos + 2 + size);
      const data = compressed ? decomp(raw) : raw;
      this.index.push([pos - start, this.len]);
      this.chunks.push(data);
      this.len += data.length;
      pos += 2 + size;
    }
    this.data = Buffer.concat(this.chunks);
  }
  read(blockOff, offset, length) {
    for (const [h, dp] of this.index) {
      if (h === blockOff) return this.data.subarray(dp + offset, dp + offset + length);
    }
    throw new Error('meta block 0x' + blockOff.toString(16) + ' not found');
  }
}

const u64 = (p) => Number(b.readBigUInt64LE(p));
const sb = {
  inodes: b.readUInt32LE(4), blockSize: b.readUInt32LE(12), comp: b.readUInt16LE(20),
  rootInode: u64(32), bytesUsed: u64(40), idTable: u64(48), inodeTable: u64(64),
  dirTable: u64(72), fragTable: u64(80), exportTable: u64(88),
};
console.log(sb);

const inodeMeta = new Meta(sb.inodeTable, sb.dirTable);
const fragBlockOff = Number(b.readBigUInt64LE(sb.fragTable));
const fragHdr = b.readUInt16LE(fragBlockOff);
const fragSize = fragHdr & 0x7fff;
const fragRaw = b.subarray(fragBlockOff + 2, fragBlockOff + 2 + fragSize);
const fragData = (fragHdr & 0x8000) === 0 ? Buffer.from(lzo1xDecompress(fragRaw)) : fragRaw;
const dirMeta = new Meta(sb.dirTable, fragBlockOff);

function parseInode(ref) {
  const block = Math.floor(ref / 0x10000);
  const off = ref % 0x10000;
  const d = inodeMeta.read(block, off, 512);
  const type = d.readUInt16LE(0), mode = d.readUInt16LE(2);
  const ino = d.readUInt32LE(8);
  let p = 16;
  const node = { type, mode, ino };
  if (type === 1) {
    node.start = d.readUInt32LE(p); node.nlink = d.readUInt32LE(p + 4);
    node.size = d.readUInt16LE(p + 8); node.offset = d.readUInt16LE(p + 10);
    node.parent = d.readUInt32LE(p + 12);
  } else if (type === 2) {
    node.start = d.readUInt32LE(p); node.frag = d.readUInt32LE(p + 4);
    node.offset = d.readUInt32LE(p + 8); node.size = d.readUInt32LE(p + 12);
    p += 16;
    let nb = Math.ceil(node.size / sb.blockSize);
    if (node.frag !== 0xffffffff) nb = Math.floor(node.size / sb.blockSize);
    node.blocks = [];
    for (let i = 0; i < nb; i++) { node.blocks.push(d.readUInt32LE(p)); p += 4; }
  } else if (type === 3) {
    node.nlink = d.readUInt32LE(p); node.size = d.readUInt32LE(p + 4);
    node.target = d.subarray(p + 8, p + 8 + node.size).toString('latin1');
  }
  return node;
}

function readDir(node) {
  const d = dirMeta.read(node.start, node.offset, node.size);
  const out = [];
  let p = 0;
  const s16 = (v) => (v & 0x8000) ? v - 0x10000 : v;
  while (p + 12 <= d.length) {
    const count = d.readUInt32LE(p), startBlock = d.readUInt32LE(p + 4);
    const baseIno = d.readUInt32LE(p + 8);
    p += 12;
    for (let i = 0; i < count + 1; i++) {
      if (p + 8 > d.length) return out;
      const offset = d.readUInt16LE(p);
      const inoDelta = s16(d.readUInt16LE(p + 2));
      const etype = d.readUInt16LE(p + 4);
      const size = d.readUInt16LE(p + 6);
      p += 8;
      const name = d.subarray(p, p + size + 1).toString('latin1').replace(/\0.*$/, '');
      p += size + 1;
      if (!name) return out;
      out.push({ name, ino: baseIno + inoDelta, type: etype, ref: (startBlock << 16) | offset });
      if (out.length > 200000) return out;
    }
  }
  return out;
}

function fragEntry(i) {
  const p = i * 16;
  return { start: Number(fragData.readBigUInt64LE(p)), size: fragData.readUInt32LE(p + 8) };
}

function readFile(node) {
  const parts = [];
  let remaining = node.size;
  for (const ent of node.blocks) {
    const compressed = (ent & 0x1000000) === 0;
    const len = ent & 0xffffff;
    const raw = b.subarray(node.start, node.start + len);
    const take = Math.min(remaining, sb.blockSize);
    if (compressed) {
      const full = decomp(raw);
      parts.push(full.subarray(0, take));
    } else {
      parts.push(raw.subarray(0, take));
    }
    node.start += len;
    remaining -= take;
  }
  if (node.frag !== 0xffffffff && remaining > 0) {
    const fe = fragEntry(node.frag);
    const compressed = (fe.size & 0x1000000) === 0;
    const len = fe.size & 0xffffff;
    const raw = b.subarray(fe.start, fe.start + len);
    const full = compressed ? decomp(raw) : raw;
    parts.push(full.subarray(node.offset, node.offset + remaining));
  }
  return Buffer.concat(parts);
}

let files = 0, dirs = 0, bytes = 0;
const tree = [];
function walk(ref, rel, depth) {
  depth = depth || 0;
  if (depth > 32) { tree.push(rel + "  [DEPTH LIMIT]"); return; }
  if (!rel) console.log("dir:", rel);

  const node = parseInode(ref);
  if (node.type === 1) {
    dirs++;
    tree.push(rel + '/');
    for (const e of readDir(node)) walk(e.ref, rel + "/" + e.name, depth + 1);
  } else if (node.type === 2) {
    if (!rel) return;
    files++; bytes += node.size;
    const p = path.join(outDir, rel);
    fs.mkdirSync(path.dirname(p), { recursive: true });
    try { fs.writeFileSync(p, readFile(node)); }
    catch (e) { tree.push(rel + '  [ERROR ' + e.message + ']'); }
  } else if (node.type === 3) {
    if (!rel) return;
    const p = path.join(outDir, rel);
    fs.mkdirSync(path.dirname(p), { recursive: true });
    try { fs.symlinkSync(node.target, p); } catch (e) { /* ignore */ }
    tree.push(rel + ' -> ' + node.target);
  }
}

fs.mkdirSync(outDir, { recursive: true });
walk(sb.rootInode, "", 0);
fs.writeFileSync(path.join(outDir, '_tree.txt'), tree.join('\n'));
console.log('files=%d dirs=%d bytes=%d', files, dirs, bytes);




