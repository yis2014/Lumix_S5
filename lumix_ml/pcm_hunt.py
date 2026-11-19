"""Find plaintext PCM audio in RAM dumps (no key needed if firmware decrypts on use).

Audio-like 16-bit PCM has strong short-lag autocorrelation and a moderate zero
crossing rate, unlike code, tables, images or random/encrypted data.
"""
import sys

import numpy as np

WIN = 8192          # bytes per analysis window
MIN_RUN = 4         # minimum consecutive audio-like windows (= 32 KiB)


def analyse(path, base):
    data = open(path, "rb").read()
    n = len(data) // WIN * WIN
    x = np.frombuffer(data[:n], dtype="<i2").reshape(-1, WIN // 2).astype(np.float64)
    rms = np.sqrt((x ** 2).mean(axis=1)) + 1e-9
    a = x[:, :-1]
    b = x[:, 1:]
    corr = (a * b).mean(axis=1) / (a.std(axis=1) * b.std(axis=1) + 1e-9)
    zcr = ((x[:, :-1] * x[:, 1:]) < 0).mean(axis=1)
    silent = (np.abs(x) < 20).mean(axis=1)
    good = (corr > 0.55) & (corr < 0.999) & (zcr > 0.01) & (zcr < 0.35) & (rms > 150) & (rms < 9000) & (silent < 0.6)

    regions = []
    i = 0
    while i < len(good):
        if good[i]:
            j = i
            while j + 1 < len(good) and good[j + 1]:
                j += 1
            if j - i + 1 >= MIN_RUN:
                regions.append((base + i * WIN, (j - i + 1) * WIN,
                                float(corr[i:j + 1].mean()), float(rms[i:j + 1].mean())))
            i = j + 1
        else:
            i += 1
    print(f"{path}: {len(regions)} audio-like region(s)")
    for addr, size, c, r in regions[:25]:
        print(f"  {addr:#010x}  {size / 1024:8.1f} KiB  corr={c:.3f} rms={r:.0f}")
    return regions


if __name__ == "__main__":
    for spec in sys.argv[1:]:
        path, base = spec.rsplit(":", 1)
        analyse(path, int(base, 0))
