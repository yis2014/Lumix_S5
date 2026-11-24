import ssl, sys, urllib.request, urllib.parse, urllib.error

CTX = ssl._create_unverified_context()
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

data = urllib.parse.urlencode({"MODEL": "S5___V29.zip", "submit": "Accepted"}).encode()
req = urllib.request.Request(
    "https://av.jpn.support.panasonic.com/support/cgi-bin/global_cs/dsc/download_s.cgi",
    data=data,
    headers={"User-Agent": UA, "Accept": "*/*", "Referer": "https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/ff/dl/s5_dl.html"},
)
try:
    r = urllib.request.urlopen(req, context=CTX, timeout=60)
    print("status", r.status)
    print("final", r.geturl())
    for k, v in r.headers.items():
        print("H", k, ":", v)
    head = r.read(4096)
    print("head bytes", len(head))
    print(repr(head[:600]))
except urllib.error.HTTPError as e:
    print("HTTPError", e.code, e.geturl())
    for k, v in e.headers.items():
        print("H", k, ":", v)
    print(repr(e.read()[:800]))
