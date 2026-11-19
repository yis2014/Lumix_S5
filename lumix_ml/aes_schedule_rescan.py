"""Aligned, endian-correct AES-128/192/256 key-schedule recovery.

Rescan raw memory with FIPS-197 word semantics.  Both storage byte orders and
all four byte alignments are tested.  A standard AES-128 test vector and
round-trip tests for every key size run before any file is scanned.

Recovered keys are candidates only; verify them against known plaintext before
claiming success.
"""
import os
import struct
import sys

import numpy as np

SBOX = np.array([
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
], dtype=np.uint32)
RCON = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1B,0x36]
CHUNK_WORDS = 1 << 20


def sub_word(w):
    w = np.asarray(w, dtype=np.uint32)
    return ((SBOX[(w >> 24) & 0xFF] << 24)
            | (SBOX[(w >> 16) & 0xFF] << 16)
            | (SBOX[(w >> 8) & 0xFF] << 8)
            | SBOX[w & 0xFF])


def subrot_be(w):
    w = np.asarray(w, dtype=np.uint32)
    rot = ((w << np.uint32(8)) & np.uint32(0xFFFFFFFF)) | (w >> np.uint32(24))
    return sub_word(rot)


def expand_key(key):
    assert len(key) in (16, 24, 32)
    nk = len(key) // 4
    total = 4 * (nk + 7)
    words = [int.from_bytes(key[i:i + 4], "big") for i in range(0, len(key), 4)]
    for i in range(nk, total):
        t = words[i - 1]
        if i % nk == 0:
            t = int(subrot_be(np.uint32(t))) ^ (RCON[i // nk - 1] << 24)
        elif nk == 8 and i % nk == 4:
            t = int(sub_word(np.uint32(t)))
        words.append((words[i - nk] ^ t) & 0xFFFFFFFF)
    return words


def verify_schedule(words, i, nk):
    total = 4 * (nk + 7)
    if i < 0 or i + total > len(words):
        return None
    w = [int(x) for x in words[i:i + total]]
    for j in range(nk, total):
        t = w[j - 1]
        if j % nk == 0:
            t = int(subrot_be(np.uint32(t))) ^ (RCON[j // nk - 1] << 24)
        elif nk == 8 and j % nk == 4:
            t = int(sub_word(np.uint32(t)))
        if w[j] != ((w[j - nk] ^ t) & 0xFFFFFFFF):
            return None
    return b"".join(struct.pack(">I", x) for x in w[:nk])


def selftest():
    # FIPS-197 Appendix A.1: first expanded word must be a0fafe17.
    key128 = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
    w128 = expand_key(key128)
    assert w128[4] == 0xA0FAFE17, hex(w128[4])
    assert w128[7] == 0x2A6C7605, hex(w128[7])
    keys = [
        key128,
        bytes.fromhex("8e73b0f7da0e6452c810f32b809079e562f8ead2522c6b7b"),
        bytes.fromhex("603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4"),
    ]
    for key in keys:
        nk = len(key) // 4
        std = np.array(expand_key(key), dtype=np.uint32)
        assert verify_schedule(std, 0, nk) == key
        # The vectorized first-round filter must select the real schedule.
        expect = std[:-nk] ^ (subrot_be(std[nk - 1:-1]) ^ np.uint32(RCON[0] << 24))
        assert int(expect[0]) == int(std[nk])
        for dtype in ("<u4", ">u4"):
            # Encode the same standard AES words in each storage byte order.
            stored = std.byteswap() if dtype == "<u4" else std
            raw = stored.astype(dtype).tobytes()
            parsed = np.frombuffer(raw, dtype=dtype)
            restored = parsed.byteswap() if dtype == "<u4" else parsed
            assert verify_schedule(restored, 0, nk) == key
    print("SELFTEST PASS: FIPS-197 AES-128 vector; AES-128/192/256; LE/BE round trips")


def scan(path, base):
    size = os.path.getsize(path)
    print(f"\nSCAN {path}\nsize={size} bytes, range={base:#x}..{base + size:#x}", flush=True)
    mm = np.memmap(path, dtype=np.uint8, mode="r")
    found = {}
    for alignment in range(4):
        usable = (size - alignment) // 4 * 4
        if usable <= 0:
            continue
        raw = mm[alignment:alignment + usable]
        for dtype in ("<u4", ">u4"):
            words = np.frombuffer(raw, dtype=dtype)
            n = len(words)
            for start in range(0, n, CHUNK_WORDS):
                w = words[start:start + CHUNK_WORDS + 60]
                if len(w) < 44:
                    continue
                std = w.byteswap() if dtype == "<u4" else w
                for nk in (4, 6, 8):
                    if len(std) < 4 * (nk + 7):
                        continue
                    expect = std[:-nk] ^ (subrot_be(std[nk - 1:-1]) ^ np.uint32(RCON[0] << 24))
                    idx = np.nonzero(expect == std[nk:])[0]
                    for i in idx:
                        i = int(i)
                        key = verify_schedule(std, i, nk)
                        if key is None:
                            continue
                        addr = base + alignment + (start + i) * 4
                        found[(addr, key)] = (dtype, nk * 32)
                        print(f"CANDIDATE AES-{nk * 32} @{addr:#x} storage={dtype} key={key.hex()}", flush=True)
        print(f"  alignment={alignment} complete; candidates={len(found)}", flush=True)
    print(f"SCAN DONE {path}: {len(found)} unique candidate(s)", flush=True)
    return found


if __name__ == "__main__":
    selftest()
    targets = sys.argv[1:] or [
        r"E:\desktop\LUMIX\highmem_9000_a000.bin",
        r"E:\desktop\LUMIX\highmem_98cd2000_a0000000.bin",
    ]
    for p in targets:
        scan(p, 0x90000000 if "9000_a000" in p else 0x98CD2000)
