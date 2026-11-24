"""First-pass structural scan of a firmware blob.

Usage: python tools/scan.py <file> [--dump N] [--strings N]
"""
import hashlib
import math
import sys
from collections import Counter


def entropy(b):
    if not b:
        return 0.0
    c = Counter(b)
    n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def read(path):
    with open(path, "rb") as f:
        return f.read()


def hexdump(b, base=0, width=16, limit=None):
    out = []
    n = len(b) if limit is None else min(limit, len(b))
    for i in range(0, n, width):
        chunk = b[i:i + width]
        hexs = " ".join("%02x" % x for x in chunk)
        text = "".join(chr(x) if 32 <= x < 127 else "." for x in chunk)
        out.append("%08x  %-*s  |%s|" % (base + i, width * 3 - 1, hexs, text))
    return "\n".join(out)


def ascii_strings(b, minlen=8):
    res = []
    cur = []
    start = 0
    for i, x in enumerate(b):
        if 32 <= x < 127:
            if not cur:
                start = i
            cur.append(chr(x))
        else:
            if len(cur) >= minlen:
                res.append((start, "".join(cur)))
            cur = []
    if len(cur) >= minlen:
        res.append((start, "".join(cur)))
    return res


def main():
    path = sys.argv[1]
    b = read(path)
    print("file       :", path)
    print("size       :", len(b), "= 0x%x" % len(b))
    print("sha256     :", hashlib.sha256(b).hexdigest())
    print("entropy    : %.4f" % entropy(b))
    print()

    print("=== first 512 bytes ===")
    print(hexdump(b, limit=512))
    print()

    print("=== entropy map (64 KiB cells, 1 char each, 128 chars/line) ===")
    CELL = 64 * 1024
    line = []
    for i in range(0, len(b), CELL):
        e = entropy(b[i:i + CELL])
        line.append(" " if e < 1 else ("." if e < 4 else (":" if e < 6.5 else ("o" if e < 7.5 else "#"))))
        if len(line) == 128:
            print("%9x %s" % (i - (len(line) - 1) * CELL, "".join(line)))
            line = []
    if line:
        print("%9x %s" % (i - (len(line) - 1) * CELL, "".join(line)))
    print()

    print("=== ASCII strings >= 8 chars (first 120) ===")
    ss = ascii_strings(b, 8)
    print("count:", len(ss))
    for off, s in ss[:120]:
        print("%08x  %s" % (off, s[:110]))


if __name__ == "__main__":
    main()
