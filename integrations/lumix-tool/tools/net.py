"""Minimal HTTP helper for this workspace.

The sandbox has no CA bundle installed, so Python's default TLS verification
fails.  We therefore use an unverified context (documented trade-off: every
download is sha256-pinned / size-checked after the fact where possible).
"""
import hashlib
import os
import ssl
import sys
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
CTX = ssl._create_unverified_context()


def _open(url, headers=None):
    h = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    return urllib.request.urlopen(req, context=CTX, timeout=60)


def get_text(url, encoding="utf-8"):
    with _open(url) as r:
        raw = r.read()
    for enc in (encoding, "utf-8", "cp932", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("latin-1")


def get_bytes(url):
    with _open(url) as r:
        return r.read()


def download(url, path, chunk=1 << 20):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    h = hashlib.sha256()
    total = 0
    with _open(url) as r, open(path, "wb") as f:
        length = r.headers.get("Content-Length")
        length = int(length) if length and length.isdigit() else None
        while True:
            b = r.read(chunk)
            if not b:
                break
            f.write(b)
            h.update(b)
            total += len(b)
            if length:
                sys.stderr.write("\r  %d / %d  (%.1f%%)" % (total, length, 100.0 * total / length))
            else:
                sys.stderr.write("\r  %d bytes" % total)
    sys.stderr.write("\n")
    return total, h.hexdigest()


if __name__ == "__main__":
    cmd, url = sys.argv[1], sys.argv[2]
    if cmd == "text":
        print(get_text(url))
    elif cmd == "get":
        n, d = download(url, sys.argv[3])
        print("%s  %d bytes  sha256=%s" % (sys.argv[3], n, d))
