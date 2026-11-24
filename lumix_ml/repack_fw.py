#!/usr/bin/env python3
"""S5 固件升级包重打包器（自制固件核心工具）。

容器格式（全部实测验证）：
  0x000:  magic "UPD\\0"
  0x024:  版本字段（4B，镜像 @0x2C4）
  0x03C:  body 大小 = 文件大小 - 0x200
  0x040:  CRC32(file[0x200:])  (zlib)
  0x200:  元数据块 "panasonic" + ECDSA 签名(r||s 64B) @0x220   ← 唯一不可重算
  0x2EC:  目录 48 项 x 92B {name[12], off, size, target, flags, sha256(明文)[32], IV[16]}
  0x142C: 468B 零洞
  0x200+off: 载荷 = AES-5-CBC(KEY, IV=aux16, 明文)

用法：
  python repack_fw.py roundtrip     # 解密盘原样回打 -> 必须与原 .bin 逐字节一致
  python repack_fw.py build OUT.bin [--ver-int 0x0a101450] [--set name.bin=文件路径]
"""
import sys, os, struct, zlib, hashlib, argparse
import numpy as np

sys.path.insert(0, r'E:\desktop\LUMIX\.workbuddy\tools')
import panasonic_aes as pa

KEY = bytes.fromhex('194364775255595d04e48de2b15e5c2c')
HEADER = 0x200
COUNT_OFF = 0x2E8
CATALOG_OFF = 0x2EC
ENTRY_SZ = 92
ROUNDS = 5
ROOT = r'E:\desktop\LUMIX'

# ---- AES-5 向量化（解密沿用 s5_keyhunt 数学；加密 = 标准正向轮） ----
SBOX = np.frombuffer(pa.SBOX, dtype=np.uint8)
INV = np.frombuffer(pa.INV, dtype=np.uint8)
_IDX = np.array([(i + 16 - 4 * (i % 4)) % 16 for i in range(16)])


def _mul(a, b):
    r = 0
    for _ in range(8):
        if b & 1:
            r ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return r


M2 = np.array([_mul(i, 2) for i in range(256)], dtype=np.uint8)
M3 = np.array([_mul(i, 3) for i in range(256)], dtype=np.uint8)
M9 = np.array([_mul(i, 9) for i in range(256)], dtype=np.uint8)
M11 = np.array([_mul(i, 11) for i in range(256)], dtype=np.uint8)
M13 = np.array([_mul(i, 13) for i in range(256)], dtype=np.uint8)
M14 = np.array([_mul(i, 14) for i in range(256)], dtype=np.uint8)


def expand_key128(key16, nr):
    keys = np.frombuffer(key16, dtype=np.uint8)[None, :]
    w = np.empty((1, 4 * (nr + 1)), dtype=np.uint32)
    w[:, :4] = keys.view('<u4').reshape(1, 4)
    rcon = 1
    for i in range(4, 4 * (nr + 1)):
        t = w[:, i - 1].copy()
        if i % 4 == 0:
            t = ((t >> 8) | (t << 24)).astype(np.uint32)
            t = (SBOX[t & 255].astype(np.uint32)
                 | (SBOX[(t >> 8) & 255].astype(np.uint32) << 8)
                 | (SBOX[(t >> 16) & 255].astype(np.uint32) << 16)
                 | (SBOX[(t >> 24) & 255].astype(np.uint32) << 24))
            t = t ^ np.uint32(rcon)
            rcon = ((rcon << 1) ^ (0x11B if rcon & 0x80 else 0)) & 0xFF
        w[:, i] = w[:, i - 4] ^ t
    return w.view(np.uint8).reshape(nr + 1, 16)


def enc_blocks(pts, rk):
    """Standard AES forward cipher, vectorized over N blocks. rk: (nr+1,16)."""
    nr = rk.shape[0] - 1
    state = pts ^ rk[0][None, :]
    for rnd in range(1, nr + 1):
        s = SBOX[state]
        sh = np.empty_like(s)
        for i in range(16):
            sh[:, i] = s[:, (i + 4 * (i % 4)) % 16]      # ShiftRows
        if rnd != nr:
            st = np.empty_like(sh)
            for col in range(0, 16, 4):
                a0, a1, a2, a3 = sh[:, col], sh[:, col + 1], sh[:, col + 2], sh[:, col + 3]
                st[:, col + 0] = M2[a0] ^ M3[a1] ^ a2 ^ a3
                st[:, col + 1] = a0 ^ M2[a1] ^ M3[a2] ^ a3
                st[:, col + 2] = a0 ^ a1 ^ M2[a2] ^ M3[a3]
                st[:, col + 3] = M3[a0] ^ a1 ^ a2 ^ M2[a3]
            sh = st
        state = sh ^ rk[rnd][None, :]                    # AddRoundKey
    return state


def dec_blocks(cts, rk):
    nr = rk.shape[0] - 1
    state = cts ^ rk[nr][None, :]
    for rnd in range(nr - 1, -1, -1):
        tmp = INV[state[:, _IDX]] ^ rk[rnd][None, :]
        if rnd == 0:
            state = tmp
        else:
            st = np.empty_like(tmp)
            for col in range(0, 16, 4):
                for row in range(4):
                    st[:, col + row] = (M14[tmp[:, col + row]]
                                        ^ M11[tmp[:, col + (row + 1) % 4]]
                                        ^ M13[tmp[:, col + (row + 2) % 4]]
                                        ^ M9[tmp[:, col + (row + 3) % 4]])
            state = st
    return state


_SBOX_P = pa.SBOX          # bytes(256)
_M2 = bytes(int(x) for x in M2)
_M3 = bytes(int(x) for x in M3)


def enc_block(pt16, sk_bytes):
    """单块正向 AES（纯 Python，与 pa.decrypt_block 同构镜像）。sk_bytes = 扁平轮密钥。"""
    nr = ROUNDS
    s = bytearray(pt16[i] ^ sk_bytes[i] for i in range(16))
    for rnd in range(1, nr + 1):
        t = bytearray(16)
        for i in range(16):
            t[i] = _SBOX_P[s[(i + 4 * (i % 4)) % 16]]
        if rnd != nr:
            st = bytearray(16)
            for col in range(0, 16, 4):
                a0, a1, a2, a3 = t[col], t[col + 1], t[col + 2], t[col + 3]
                st[col + 0] = _M2[a0] ^ _M3[a1] ^ a2 ^ a3
                st[col + 1] = a0 ^ _M2[a1] ^ _M3[a2] ^ a3
                st[col + 2] = a0 ^ a1 ^ _M2[a2] ^ _M3[a3]
                st[col + 3] = _M3[a0] ^ a1 ^ a2 ^ _M2[a3]
            t = st
        base = 16 * rnd
        for i in range(16):
            t[i] ^= sk_bytes[base + i]
        s = t
    return bytes(s)


def cbc_crypt(data, rk, iv, encrypt):
    n = len(data) // 16
    blocks = np.frombuffer(data, dtype=np.uint8).reshape(n, 16)
    if encrypt:
        sk = rk.tobytes()   # 扁平轮密钥
        out = bytearray(len(data))
        prev = bytes(iv)
        mv = memoryview(data)
        for i in range(n):
            x = bytes(mv[16 * i + j] ^ prev[j] for j in range(16))
            c = enc_block(x, sk)
            out[16 * i:16 * i + 16] = c
            prev = c
        return bytes(out)
    # P_i = D(C_i) ^ C_{i-1}：可整段向量化
    dec = dec_blocks(blocks, rk)
    prev = np.empty((n, 16), dtype=np.uint8)
    prev[0] = np.frombuffer(iv, dtype=np.uint8)
    if n > 1:
        prev[1:] = blocks[:-1]
    return (dec ^ prev).tobytes()


def selftest():
    rk = expand_key128(np.frombuffer(KEY, dtype=np.uint8), ROUNDS)
    for _ in range(8):
        pt = os.urandom(16)
        # vector enc -> reference dec
        ct = enc_blocks(np.frombuffer(pt, dtype=np.uint8)[None, :], rk)[0].tobytes()
        ref = pa.decrypt_block(ct, pa.expand_key(KEY, ROUNDS), ROUNDS)
        assert ref == pt, f'enc/dec mismatch: {pt.hex()} -> {ct.hex()} -> {ref.hex()}'
    # CBC roundtrip
    data = os.urandom(4096)
    iv = os.urandom(16)
    ct = cbc_crypt(data, rk, iv, encrypt=True)
    pt = cbc_crypt(ct, rk, iv, encrypt=False)
    assert pt == data
    # vs reference decrypt_cbc
    iv2 = os.urandom(16)
    ct2 = cbc_crypt(data, rk, iv2, encrypt=True)
    assert pa.decrypt_cbc(ct2, KEY, iv2, 5) == data
    print('selftest: PASS')


# ---- 容器解析/重建 ----
class Entry:
    def __init__(s, name, off, size, target, flags, digest, aux):
        s.name, s.off, s.size, s.target, s.flags = name, off, size, target, flags
        s.digest, s.aux = digest, aux

    def pack(s):
        return (s.name.encode()[:12].ljust(12, b'\0')
                + struct.pack('<4I', s.off, s.size, s.target, s.flags)
                + s.digest + s.aux)


def parse_catalog(fw):
    n = struct.unpack_from('<I', fw, COUNT_OFF)[0]
    out = []
    for i in range(n):
        p = CATALOG_OFF + ENTRY_SZ * i
        name = fw[p:p + 12].split(b'\0')[0].decode()
        off, size, target, flags = struct.unpack_from('<4I', fw, p + 12)
        out.append(Entry(name, off, size, target, flags, fw[p + 28:p + 60], fw[p + 60:p + 76]))
    return out


def repack(src_bin, plain_dir, out_path, ver_int=None, overrides=None):
    fw = open(src_bin, 'rb').read()
    entries = parse_catalog(fw)
    rk = expand_key128(np.frombuffer(KEY, dtype=np.uint8), ROUNDS)

    out = bytearray(fw)                     # 原文件打底：头部/元数据/零洞/未改区全部保留
    for e in entries:
        p = os.path.join(plain_dir, f'{e.name}.bin')
        if overrides and e.name in overrides:
            pt = open(overrides[e.name], 'rb').read()
        elif os.path.exists(p):
            pt = open(p, 'rb').read()
        elif e.size == 0:
            pt = b''
        else:
            raise FileNotFoundError(p)
        if len(pt) != e.size:
            raise ValueError(f'{e.name}: 明文 {len(pt)} != 目录 {e.size}（保持大小不变才能免重排）')

        if e.aux == b'\x00' * 16:
            ct = pt
        else:
            ct = cbc_crypt(pt, rk, e.aux, encrypt=True)
        assert len(ct) == e.size
        pos = HEADER + e.off
        out[pos:pos + e.size] = ct
        new_digest = hashlib.sha256(pt).digest()
        cp = CATALOG_OFF + ENTRY_SZ * entries.index(e)
        out[cp + 28:cp + 60] = new_digest

    if ver_int is not None:
        struct.pack_into('<I', out, 0x24, ver_int)
        struct.pack_into('<I', out, 0x2C4, ver_int)

    body_size = len(out) - HEADER
    struct.pack_into('<I', out, 0x3C, body_size)
    struct.pack_into('<I', out, 0x40, zlib.crc32(bytes(out[HEADER:])) & 0xFFFFFFFF)

    open(out_path, 'wb').write(bytes(out))
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['selftest', 'roundtrip', 'build'])
    ap.add_argument('out', nargs='?')
    ap.add_argument('--src', default=os.path.join(ROOT, 'S5___V29.bin'))
    ap.add_argument('--plain', default=os.path.join(ROOT, 'analysis', 'decrypted_S5___V29'))
    ap.add_argument('--ver-int', type=lambda x: int(x, 0), default=None)
    ap.add_argument('--set', action='append', default=[],
                    help='name.bin=/path/to/plain.bin 覆盖单个分区明文')
    a = ap.parse_args()

    selftest()
    if a.cmd == 'selftest':
        return
    if a.cmd == 'roundtrip':
        out = os.path.join(ROOT, 'analysis', 'repack_roundtrip_test.bin')
        repack(a.src, a.plain, out)
        orig = open(a.src, 'rb').read()
        new = open(out, 'rb').read()
        if orig == new:
            print(f'roundtrip: PASS  ({len(new)} bytes, 逐字节一致)')
        else:
            diff = [i for i in range(min(len(orig), len(new))) if orig[i] != new[i]]
            print(f'roundtrip: FAIL  {len(diff)} bytes differ, first at {diff[0]:#x}' if diff
                  else f'roundtrip: FAIL  size {len(orig)} vs {len(new)}')
        return
    if a.cmd == 'build':
        if not a.out:
            ap.error('build 需要输出路径')
        ov = {}
        for spec in a.set:
            k, v = spec.split('=', 1)
            ov[k] = v
        repack(a.src, a.plain, a.out, ver_int=a.ver_int, overrides=ov)
        fw = open(a.out, 'rb').read()
        print(f'built: {a.out} ({len(fw)} bytes)')
        print(f'  version field: {struct.unpack_from("<I", fw, 0x24)[0]:#010x}')
        print(f'  body size @0x3c: {struct.unpack_from("<I", fw, 0x3C)[0]:#x}')
        print(f'  crc32 @0x40: {struct.unpack_from("<I", fw, 0x40)[0]:#010x} '
              f'(recomputed ok)')
        print('  注意: 0x220 处 ECDSA 签名沿用原文件，内容被改动后验签会失败——')
        print('        需要 RAM 补丁掉 postboot 验签函数，或走直接写 NAND 路线。')


if __name__ == '__main__':
    main()
