#!/usr/bin/env python3
"""Batch-decrypt all S5 firmware partitions with the recovered AES key.

Algorithm: 5-round AES-128-CBC
Key:       19 43 64 77 52 55 59 5d 04 e4 8d e2 b1 5e 5c 2c
IV:        partition catalog aux16 field
Offset:    partitions.json offset + 0x200 (UPD header size)

Vectorized decryption over many blocks per key (same math as s5_keyhunt).
For each partition: decrypt -> verify SHA-256 against catalog h1 -> save plaintext.
Falls back to raw copy when raw SHA matches (unencrypted partitions).
"""
import sys, os, json, hashlib, time
import numpy as np

sys.path.insert(0, r'E:\desktop\LUMIX\.workbuddy\tools')
import panasonic_aes as pa

KEY = bytes.fromhex('194364775255595d04e48de2b15e5c2c')
HEADER = 0x200
ROOT = r'E:\desktop\LUMIX'
PART_JSON = os.path.join(ROOT, 'analysis', 'partitions.json')
OUT_ROOT = os.path.join(ROOT, 'analysis')
ROUNDS = 5

SBOX = np.frombuffer(pa.SBOX, dtype=np.uint8)
INV = np.frombuffer(pa.INV, dtype=np.uint8)

# InvShiftRows source index for each output position
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


M9 = np.array([_mul(i, 9) for i in range(256)], dtype=np.uint8)
M11 = np.array([_mul(i, 11) for i in range(256)], dtype=np.uint8)
M13 = np.array([_mul(i, 13) for i in range(256)], dtype=np.uint8)
M14 = np.array([_mul(i, 14) for i in range(256)], dtype=np.uint8)


def expand_key128(key16, nr):
    """key16: (16,) uint8 -> round keys (nr+1, 16) uint8."""
    keys = np.frombuffer(key16, dtype=np.uint8)[None, :]
    nk = 4
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


def batch_decrypt_blocks(cts, rk):
    """cts: (N,16) uint8; rk: (nr+1,16) -> (N,16) plaintext."""
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


def decrypt_cbc_fast(ct, rk, iv):
    """Vectorized CBC decrypt of whole buffer (multiple of 16)."""
    n = len(ct) // 16
    blocks = np.frombuffer(ct, dtype=np.uint8).reshape(n, 16)
    pt = batch_decrypt_blocks(blocks, rk)
    # CBC: pt[i] ^= ct[i-1]; pt[0] ^= iv
    prev = np.empty_like(blocks)
    prev[0] = np.frombuffer(iv, dtype=np.uint8)
    if n > 1:
        prev[1:] = blocks[:-1]
    pt ^= prev
    return pt.tobytes()


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def main():
    catalog = json.load(open(PART_JSON, encoding='utf-8'))
    rk = expand_key128(np.frombuffer(KEY, dtype=np.uint8), ROUNDS)

    # self-check against reference impl
    test = b'\x00' * 16
    ref = pa.decrypt_block(test, pa.expand_key(KEY, ROUNDS), ROUNDS)
    got = batch_decrypt_blocks(np.frombuffer(test, dtype=np.uint8)[None, :], rk)[0].tobytes()
    assert got == ref, f'self-check failed: {got.hex()} != {ref.hex()}'
    print('vectorized impl self-check: PASS')

    for ver in ['S5___V29.bin', 'S5___V28.bin', 'S5m2_V37.bin']:
        rows = catalog[ver]
        fw_path = os.path.join(ROOT, ver)
        if not os.path.exists(fw_path):
            print(f'[skip] {ver}: file not found')
            continue
        print(f'\n===== {ver} =====')
        fw = open(fw_path, 'rb').read()
        out_dir = os.path.join(OUT_ROOT, f'decrypted_{ver.replace(".bin", "")}')
        os.makedirs(out_dir, exist_ok=True)

        t0 = time.time()
        ok = fail = skip = 0
        total_bytes = 0
        results = []
        for r in rows:
            name = r['name']
            off = r['offset'] + HEADER
            size = r['size']
            aux = bytes.fromhex(r['aux16'])
            want = r['stored_sha256']

            if size == 0:
                skip += 1
                results.append((name, 'SKIP(0)', ''))
                continue

            ct = fw[off:off + size]
            if len(ct) != size:
                fail += 1
                results.append((name, 'FAIL(trunc)', ''))
                continue

            got, how = None, ''
            if aux == b'\x00' * 16:
                h = sha256(ct)
                if h == want:
                    got, how = ct, 'raw'
            if got is None:
                try:
                    pt = decrypt_cbc_fast(ct, rk, aux)
                    h = sha256(pt)
                    if h == want:
                        got, how = pt, 'aes5-cbc'
                    else:
                        h2 = sha256(ct)
                        if h2 == want:
                            got, how = ct, 'raw-fallback'
                        else:
                            fail += 1
                            results.append((name, 'FAIL(hash)', h[:16]))
                            continue
                except Exception as e:
                    fail += 1
                    results.append((name, f'FAIL({type(e).__name__})', str(e)[:30]))
                    continue

            open(os.path.join(out_dir, f'{name}.bin'), 'wb').write(got)
            ok += 1
            total_bytes += len(got)
            results.append((name, 'OK ' + how, want[:16]))

        dt = time.time() - t0
        print(f'{"name":<14} {"result":<16} {"h1[:16]":<18}')
        for name, res, h in results:
            print(f'{name:<14} {res:<16} {h:<18}')
        rate = total_bytes / (1 << 20) / dt if dt > 0 else 0
        print(f'\n{ver}: OK={ok} FAIL={fail} SKIP={skip}  '
              f'{total_bytes/(1<<20):.1f} MiB in {dt:.1f}s ({rate:.1f} MiB/s)')
        print(f'-> {out_dir}')


if __name__ == '__main__':
    main()
