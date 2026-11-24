import struct, sys

def call_target(hw1, hw2, pc):
    if (hw1 & 0xF800) != 0xF000:
        return None
    if (hw2 & 0xC000) != 0xC000:
        return None
    # bit12=1 -> BL, bit12=0 -> BLX
    s = (hw1 >> 10) & 1
    imm10 = hw1 & 0x3FF
    j1 = (hw2 >> 13) & 1
    j2 = (hw2 >> 11) & 1
    i1 = 1 - (j1 ^ s)
    i2 = 1 - (j2 ^ s)
    imm = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | ((hw2 & 0x7FF) << 1)
    if s:
        imm -= 1 << 25
    return (pc + 4 + imm) & 0xFFFFFFFF

path, target_str = sys.argv[1], sys.argv[2]
base = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0
target = int(target_str, 16)
data = open(path, 'rb').read()
hits = []
for off in range(0, len(data) - 4, 2):
    hw1 = struct.unpack_from('<H', data, off)[0]
    if (hw1 & 0xF800) != 0xF000:
        continue
    hw2 = struct.unpack_from('<H', data, off + 2)[0]
    t = call_target(hw1, hw2, base + off)
    if t is not None and (t & ~1) == (target & ~1):
        hits.append((base + off, 'blx' if (hw2 & 0x1000) == 0 else 'bl'))
print('target 0x%X: %d call sites' % (target, len(hits)))
for a, k in hits[:10]:
    print('  0x%X %s' % (a, k))
