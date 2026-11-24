"""Minimal squashfs 4.0 reader for the S5 slram rootfs copies.

Both slram rootfs images store every metadata block uncompressed (header high
bit set), so inodes and directories can be parsed without an LZO library.
File data blocks may still be compressed; those are reported, not extracted.
"""
import os
import struct
import sys

META_HDR = 2


class Meta:
    """A metadata table: concatenated uncompressed data plus block index."""

    def __init__(self, buf, start, end):
        self.index = []          # (header_stream_offset, data_pos_in_stream)
        self.data = bytearray()  # concatenated uncompressed data
        pos = start
        while pos < end:
            hdr = struct.unpack_from("<H", buf, pos)[0]
            size = hdr & 0x7FFF
            compressed = (hdr & 0x8000) == 0
            if compressed:
                raise RuntimeError("compressed metadata block at 0x%X" % pos)
            self.index.append((pos - start, len(self.data)))
            self.data += buf[pos + 2:pos + 2 + size]
            pos += 2 + size
        self.end = pos

    def read(self, block_off, offset, length):
        for hdr_off, data_pos in self.index:
            if hdr_off == block_off:
                p = data_pos + offset
                return bytes(self.data[p:p + length])
        raise RuntimeError("metadata block 0x%X not found" % block_off)

    def stream(self):
        return bytes(self.data)


class Squash:
    def __init__(self, path):
        self.buf = open(path, "rb").read()
        f = struct.unpack("<IIIIIHHHHHHQQQQQQQQ", self.buf[:96])
        (self.magic, self.inodes, self.mkfs_time, self.block_size, self.fragments,
         self.compression, self.block_log, self.flags, self.no_ids, self.major,
         self.minor, self.root_inode, self.bytes_used, self.id_table,
         self.xattr_id_table, self.inode_table, self.dir_table,
         self.frag_table, self.export_table) = f
        if self.magic != 0x73717368:
            raise RuntimeError("not squashfs")
        self.inode_meta = Meta(self.buf, self.inode_table, self.dir_table)
        self.dir_meta = Meta(self.buf, self.dir_table, self.frag_table)

    def inode(self, ref):
        block = ref >> 16
        off = ref & 0xFFFF
        data = self.inode_meta.read(block, off, 256)
        return self.parse_inode(data)

    def parse_inode(self, d):
        itype, mode, uid, guid, mtime, ino = struct.unpack_from("<HHHHII", d, 0)
        p = 16
        node = {"type": itype, "mode": mode, "uid": uid, "guid": guid,
                "mtime": mtime, "ino": ino}
        if itype == 1:  # basic dir
            start, nlink, size, offset, parent = struct.unpack_from("<IIHHI", d, p)
            node.update(start=start, nlink=nlink, size=size, offset=offset, parent=parent)
        elif itype == 2:  # basic file
            start, frag, offset, size = struct.unpack_from("<IIII", d, p)
            p += 16
            nblocks = (size + self.block_size - 1) // self.block_size
            if frag != 0xFFFFFFFF:
                nblocks = size // self.block_size
            sizes = list(struct.unpack_from("<%dI" % nblocks, d, p))
            node.update(start=start, frag=frag, offset=offset, size=size, blocks=sizes)
        elif itype == 3:  # symlink
            nlink, size = struct.unpack_from("<II", d, p)
            node.update(nlink=nlink, size=size, target=d[p + 8:p + 8 + size])
        else:
            node.update(raw=d[p:p + 64].hex())
        return node

    def read_dir(self, node):
        data = self.dir_meta.read(node["start"], node["offset"], node["size"] + 256)
        entries = []
        p = 0
        while p + 12 <= len(data):
            count, start, ino, etype, size = struct.unpack_from("<IIII", data, p)
            p += 12
            name = data[p:p + size + 1]
            p += size + 1
            name = name.split(b"\0")[0].decode("latin-1")
            if not name:
                break
            entries.append((name, ino, etype, start))
            if len(entries) > 100000:
                break
        return entries


def walk(sq, ref, path, out, depth=0):
    node = sq.inode(ref)
    if node["type"] == 1:
        out.append("%s/  (dir, %d entries)" % (path, node.get("nlink", 0)))
        try:
            for name, ino, etype, start in sq.read_dir(node):
                walk(sq, start, path + "/" + name, out, depth + 1)
        except Exception as e:
            out.append("%s/  ERROR reading dir: %s" % (path, e))
    elif node["type"] == 2:
        comp = sum(1 for b in node["blocks"] if not (b & 0x1000000))
        out.append("%s  (file, %d bytes, %d blocks, %d compressed)" %
                   (path, node["size"], len(node["blocks"]), comp))
    elif node["type"] == 3:
        out.append("%s -> %s  (symlink)" % (path, node.get("target", b"").decode("latin-1")))
    else:
        out.append("%s  (inode type %d)" % (path, node["type"]))


def main():
    path = sys.argv[1]
    out_path = sys.argv[2]
    sq = Squash(path)
    print("inodes=%d block=%d comp=%d used=0x%X inode_tab=0x%X dir_tab=0x%X" %
          (sq.inodes, sq.block_size, sq.compression, sq.bytes_used,
           sq.inode_table, sq.dir_table))
    out = []
    walk(sq, sq.root_inode, "", out)
    open(out_path, "w", encoding="utf-8").write("\n".join(out))
    print("wrote", len(out), "entries ->", out_path)


if __name__ == "__main__":
    main()
