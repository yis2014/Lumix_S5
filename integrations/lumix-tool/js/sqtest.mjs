// Feasibility test: parse the S5 squashfs superblock and decompress the first
// metadata block with the pure-TS LZO1X implementation.
import fs from 'fs';
import { lzo1xDecompress } from 'lzo1x';

const img = fs.readFileSync('out/rootfs.squashfs');
const u32 = (o) => img.readUInt32LE(o);
const u16 = (o) => img.readUInt16LE(o);
const u64 = (o) => Number(img.readBigUInt64LE(o));

const sb = {
  magic: u32(0),
  inodes: u32(4),
  mkfsTime: u32(8),
  blockSize: u32(12),
  fragments: u32(16),
  compression: u16(20),
  blockLog: u16(22),
  flags: u16(24),
  noIds: u16(26),
  major: u16(28),
  minor: u16(30),
  rootInode: u64(32),
  bytesUsed: u64(40),
  idTable: u64(48),
  xattrIdTable: u64(56),
  inodeTable: u64(64),
  dirTable: u64(72),
  fragTable: u64(80),
  exportTable: u64(88),
};
console.log('superblock', sb);

function readMeta(buf, start) {
  const hdr = buf.readUInt16LE(start);
  const size = hdr & 0x7fff;
  const uncompressed = (hdr & 0x8000) !== 0;
  const data = buf.subarray(start + 2, start + 2 + size);
  if (uncompressed) return { data, next: start + 2 + size, raw: true };
  const out = lzo1xDecompress(data, 8192);
  return { data: Buffer.from(out), next: start + 2 + size, raw: false };
}

const m = readMeta(img, sb.inodeTable);
console.log('inode metadata block: raw=%s bytes=%d', m.raw, m.data.length);
console.log('first 32:', m.data.subarray(0, 32).toString('hex'));
const inodeType = m.data.readUInt16LE(0);
const mode = m.data.readUInt16LE(2);
console.log('first inode: type=%d mode=0o%s', inodeType, mode.toString(8));
