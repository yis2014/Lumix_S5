#!/usr/bin/env python3
"""ECDSA 公钥恢复：用三份官方容器的签名反解公钥，交叉验证。

原理：给 (r, s) 与消息哈希 e，可反解 Q = r^-1 (sR - eG)。
R 由 r 反推（y 有正负两个候选）。每次恢复必得一个"公钥"，
但只有 消息解析方式/曲线/哈希 全部猜对时，三份不同容器才会解出**同一个 Q**。
误判概率 2^-256 级，故交集非空即为定论。

  python ecdsa_recover.py selftest
  python ecdsa_recover.py run
"""
import hashlib
import itertools
import sys


# ---------------- 曲线 ----------------
class Curve:
    def __init__(self, name, p, a, b, gx, gy, n):
        self.name, self.p, self.a, self.b, self.n = name, p, a, b, n
        self.G = (gx, gy)

    def on(self, P):
        if P is None:
            return True
        x, y = P
        return (y * y - (x * x * x + self.a * x + self.b)) % self.p == 0


P256 = Curve(
    "P-256",
    0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF,
    -3,
    0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B,
    0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
    0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5,
    0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551,
)

K256 = Curve(
    "secp256k1",
    0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F,
    0, 7,
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
    0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141,
)

BP256 = Curve(
    "brainpoolP256r1",
    0xA9FB57DBA1EEA9BC3E660A909D838D726E3BF623D52620282013481D1F6E5377,
    0x7D5A0975FC2C3057EEF67530417AFFE7FB8055C126DC5C6CE94A4B44F330B5D9,
    0x26DC5C6CE94A4B44F330B5D9BBD77CBF958416295CF7E1CE6BCCDC18FF8C07B6,
    0x8BD2AEB9CB7E57CB2C4B482FFC81B7AFB9DE27E1E3BD23C23A4453BD9ACE3262,
    0x547EF835C3DAC4FD97F8461A14611DC9C27745132DED8E545C1D54C72F046997,
    0xA9FB57DBA1EEA9BC3E660A909D838D718C397AA3B561A6F7901E0E82974856A7,
)

CURVES = [P256, K256, BP256]


# ---------------- 椭圆曲线运算（Jacobian） ----------------
def _dbl(c, P):
    if P is None:
        return None
    X, Y, Z = P
    if Y == 0:
        return None
    p = c.p
    YY = Y * Y % p
    S = 4 * X * YY % p
    M = (3 * X * X + c.a * pow(Z, 4, p)) % p
    X3 = (M * M - 2 * S) % p
    Y3 = (M * (S - X3) - 8 * YY * YY) % p
    Z3 = 2 * Y * Z % p
    return (X3, Y3, Z3)


def _add(c, P, Q):
    if P is None:
        return Q
    if Q is None:
        return P
    p = c.p
    X1, Y1, Z1 = P
    X2, Y2, Z2 = Q
    Z1Z1 = Z1 * Z1 % p
    Z2Z2 = Z2 * Z2 % p
    U1 = X1 * Z2Z2 % p
    U2 = X2 * Z1Z1 % p
    S1 = Y1 * Z2 * Z2Z2 % p
    S2 = Y2 * Z1 * Z1Z1 % p
    if U1 == U2:
        if S1 != S2:
            return None
        return _dbl(c, P)
    H = (U2 - U1) % p
    R = (S2 - S1) % p
    HH = H * H % p
    HHH = H * HH % p
    V = U1 * HH % p
    X3 = (R * R - HHH - 2 * V) % p
    Y3 = (R * (V - X3) - S1 * HHH) % p
    Z3 = H * Z1 * Z2 % p
    return (X3, Y3, Z3)


def _to_affine(c, P):
    if P is None:
        return None
    X, Y, Z = P
    zi = pow(Z, -1, c.p)
    zi2 = zi * zi % c.p
    return (X * zi2 % c.p, Y * zi2 * zi % c.p)


def mul(c, k, P):
    """k*P，返回仿射坐标。"""
    k %= c.n
    if k == 0 or P is None:
        return None
    J = (P[0], P[1], 1)
    R = None
    while k:
        if k & 1:
            R = _add(c, R, J)
        J = _dbl(c, J)
        k >>= 1
    return _to_affine(c, R)


def mul2(c, k1, P1, k2, P2):
    """k1*P1 + k2*P2（Shamir 技巧）。"""
    J1 = (P1[0], P1[1], 1)
    J2 = (P2[0], P2[1], 1)
    J12 = _add(c, J1, J2)
    R = None
    n = max(k1.bit_length(), k2.bit_length())
    for i in range(n - 1, -1, -1):
        R = _dbl(c, R)
        b1 = (k1 >> i) & 1
        b2 = (k2 >> i) & 1
        if b1 and b2:
            R = _add(c, R, J12)
        elif b1:
            R = _add(c, R, J1)
        elif b2:
            R = _add(c, R, J2)
    return _to_affine(c, R)


def compress(c, Q):
    if Q is None:
        return None
    x, y = Q
    return bytes([2 | (y & 1)]) + x.to_bytes(32, "big")


# ---------------- 恢复 ----------------
def recover(c, r, s, e):
    """返回两个候选公钥（R 的 y 取正/负）。"""
    if not (0 < r < c.n and 0 < s < c.n):
        return []
    p = c.p
    alpha = (pow(r, 3, p) + c.a * r + c.b) % p
    # p % 4 == 3 => sqrt = a^((p+1)/4)
    beta = pow(alpha, (p + 1) // 4, p)
    if beta * beta % p != alpha:
        return []
    out = []
    rinv = pow(r, -1, c.n)
    for y in (beta, (p - beta) % p):
        R = (r, y)
        if not c.on(R):
            continue
        # Q = r^-1 (sR - eG)
        Q = mul2(c, s * rinv % c.n, R, (-e * rinv) % c.n, c.G)
        if Q is not None:
            out.append(Q)
    return out


def verify(c, Q, r, s, e):
    if Q is None:
        return False
    w = pow(s, -1, c.n)
    X = mul2(c, e * w % c.n, c.G, r * w % c.n, Q)
    if X is None:
        return False
    return X[0] % c.n == r


# ---------------- 容器解析 ----------------
def regions(d):
    """候选消息区。返回 {名字: 字节}。"""
    import struct
    n = struct.unpack_from("<I", d, 0x2E8)[0]
    dirend = 0x2EC + n * 0x5C
    r = {
        "whole": d,
        "0x200..eof": d[0x200:],
        "0x2a0..eof": d[0x2A0:],
        "0x2ec..eof": d[0x2EC:],
        "0x1600..eof": d[0x1600:],
        "0x0..0x200": d[:0x200],
        "0x0..0x220": d[:0x220],
        "0x0..0x2a0": d[:0x2A0],
        "0x0..dir_end": d[:dirend],
        "dir_only": d[0x2EC:dirend],
        "dir+payload": d[0x2EC:],
        "hdr_no_sig": d[:0x220] + d[0x260:0x2A0],
        "body_no_sig": d[0x200:0x220] + d[0x260:],
        "0x2a0..0x2ec": d[0x2A0:0x2EC],
        "sig_region_only": d[0x220:0x260],
    }
    return r


ALGS = {
    "sha256": hashlib.sha256,
    "sha1": hashlib.sha1,
    "sha384": hashlib.sha384,
    "sha512": hashlib.sha512,
    "md5": hashlib.md5,
}


def selftest():
    # 用 P-256 造一个已知签名，验证恢复能解出原公钥
    c = P256
    d = 0x1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF
    Q = mul(c, d, c.G)
    msg = b"lumix selftest"
    e = int.from_bytes(hashlib.sha256(msg).digest(), "big") % c.n
    k = 0x0FEDCBA9876543210FEDCBA9876543210FEDCBA9876543210FEDCBA987654321
    R = mul(c, k, c.G)
    r = R[0] % c.n
    s = pow(k, -1, c.n) * (e + r * d) % c.n
    cands = recover(c, r, s, e)
    ok = any(compress(c, Qc) == compress(c, Q) for Qc in cands)
    print("自检: 签名有效=%s 恢复命中原公钥=%s" % (verify(c, Q, r, s, e), ok))
    # 错误消息必须恢复出别的公钥
    cands2 = recover(c, r, s, e ^ 1)
    print("自检: 错误哈希给出不同公钥=%s"
          % all(compress(c, x) != compress(c, Q) for x in cands2))
    return ok


def run(files, curve_names=None):
    curves = [c for c in CURVES if not curve_names or c.name in curve_names]
    data = {}
    for f in files:
        d = open(f, "rb").read()
        data[f] = d
        print("%-22s %d 字节  sig=%s" % (f, len(d), d[0x220:0x240].hex()[:16] + "..."))

    # 每容器每区每算法只算一次
    digests = {}
    for f, d in data.items():
        rs = regions(d)
        per = {}
        for rn, blob in rs.items():
            for an in ALGS:
                per[(rn, an)] = ALGS[an](blob).digest()
        digests[f] = per
        print("  %s: %d 区 × %d 算法" % (f, len(rs), len(ALGS)))

    total_hit = 0
    for c in curves:
        for rn in regions(next(iter(data.values()))):
            for an in ALGS:
                # 每容器各自用同区同算法求 e
                votes = {}
                for f, d in data.items():
                    blob = d[0x220:0x260]
                    h = digests[f][(rn, an)]
                    e = int.from_bytes(h, "big") % c.n
                    r = int.from_bytes(blob[:32], "big")
                    s = int.from_bytes(blob[32:64], "big")
                    ks = [compress(c, Q) for Q in recover(c, r, s, e)]
                    for k in ks:
                        votes.setdefault(k, set()).add(f)
                for k, fs in votes.items():
                    if len(fs) == len(data):
                        print("\n*** 命中：曲线=%s 区=%s 哈希=%s" % (c.name, rn, an))
                        print("    公钥(压缩) = %s" % k.hex())
                        total_hit += 1
    print("\n候选组合共 %d 组，交叉验证命中 %d 组"
          % (len(curves) * len(regions(next(iter(data.values())))) * len(ALGS), total_hit))
    return total_hit


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    if cmd == "selftest":
        selftest()
    elif cmd == "run":
        base = "E:/desktop/LUMIX/"
        run([base + "S5___V28.bin", base + "S5___V29.bin", base + "S5m2_V37.bin"])
