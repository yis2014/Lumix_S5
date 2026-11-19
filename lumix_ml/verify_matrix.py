"""Find the input encoding that makes the genuine S5 V2.9 signature verify.

The wrapper at 0x868c08c6 returns 0 = valid, 1 = invalid (same convention as G100).
We try the small matrix of digest / signature / public-key byte orders.
"""
import hashlib
import itertools
import json

import emulate_verify as ev

digest = ev.digest
signature = ev.signature
pubkey = bytes(ev.image[ev.PUBKEY_VIRT - ev.VIRT_BASE: ev.PUBKEY_VIRT - ev.VIRT_BASE + 64])


def rev32(b):
    return b[:32][::-1] + b[32:][::-1]


DIGESTS = {"be": digest, "le": digest[::-1]}
SIGS = {"file": signature, "rev32": rev32(signature), "rev64": signature[::-1]}
PUBS = {"stored": pubkey, "rev32": rev32(pubkey)}

results = []
for (dn, d), (sn, s), (pn, p) in itertools.product(DIGESTS.items(), SIGS.items(), PUBS.items()):
    # public key is supplied by patching a scratch copy and pointing r0 at it
    ev_image_pub = ev.PUBKEY_VIRT
    import emulate_verify
    orig_run = emulate_verify.run

    def run_with_pub(hash_bytes, sig_bytes, pub_bytes):
        # temporarily replace the key bytes in the mapped image
        old = ev.image
        mutable = bytearray(old)
        off = ev.PUBKEY_VIRT - ev.VIRT_BASE
        mutable[off:off + 64] = pub_bytes
        ev.image = bytes(mutable)
        try:
            return orig_run(hash_bytes, sig_bytes)
        finally:
            ev.image = old

    r, count = run_with_pub(d, s, p)
    ok = (r == 0)
    print(f"digest={dn:2s} sig={sn:5s} pub={pn:6s} -> r0={r} ({count} ins){'  <== VALID' if ok else ''}", flush=True)
    results.append({"digest": dn, "sig": sn, "pub": pn, "r0": r, "instructions": count})
    if ok:
        # negative control: corrupt one digest bit, must become invalid (1)
        bad = bytearray(d)
        bad[0] ^= 1
        r_bad, _ = run_with_pub(bytes(bad), s, p)
        print(f"    negative control (corrupted digest) -> r0={r_bad}", flush=True)
        results[-1]["negative_control_r0"] = r_bad
        break

open(r"E:\desktop\LUMIX\verify_encoding_matrix.json", "w").write(json.dumps(results, indent=2))
