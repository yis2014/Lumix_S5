"""Locate audio_soundplay_get_data() by finding code that references its debug string.

The string "audio_soundplay_get_data(id:%d freq:%d adr:0x%x size:%d) return %d"
lives at physical 0x86E35486 (virtual 0x06E35486). Thumb-2 code materialises such
addresses with a movw/movt pair, so a plain 32-bit literal search finds nothing.
"""
import struct

from movw_scan import mov_patterns
from thumb_calls import disasm

BIN = r"E:\desktop\LUMIX\program_0x86280000.bin"
BASE = 0x86280000
blob = open(BIN, "rb").read()

TARGETS = [
    0x06E35486,  # audio_soundplay_get_data(...) debug string, virtual
    0x86E35486,  # same, physical form
    0x064784C2,  # AUDIO_PlaySound(id:%d vol:%d), virtual
    0x864784C2,  # same, physical form
    0x06478486,  # AUDIO_soundplay_task receive(...), virtual
]

for TARGET in TARGETS:
    LOW, HIGH = TARGET & 0xFFFF, TARGET >> 16
    movw = {pat: rd for rd, pat in mov_patterns(TARGET, movt=False)}
    movt = {pat: rd for rd, pat in mov_patterns(HIGH << 16, movt=True)}
    hits = []
    for pat, rd in movw.items():
        start = 0
        while True:
            i = blob.find(pat, start)
            if i < 0:
                break
            start = i + 2
            for off in (4, 6, 8):
                j = i + off
                if blob[j:j + 4] in movt and movt[blob[j:j + 4]] == rd:
                    hits.append(BASE + i)
                    break
    print(f"movw/movt references to 0x{TARGET:08x}: {len(hits)} -> {[hex(h) for h in hits[:6]]}")
    for h in hits[:2]:
        print(disasm(blob, h - 0x30, 0x50))
