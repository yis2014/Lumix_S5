import struct
import sys

d = open(sys.argv[1], "rb").read()
magic, total, ods, odstr, omr, ver, lcv, cpuid, sds, sdst = struct.unpack(">10I", d[:40])
print(f"totalsize={total} struct={ods:#x} strings={odstr:#x} ver={ver}")
STR = d[odstr:odstr + sds]


def name_of(off):
    end = STR.find(b"\x00", off)
    return STR[off:end].decode("ascii", "replace")


p = ods
depth = 0
while p < len(d) - 4:
    tok = struct.unpack(">I", d[p:p + 4])[0]
    p += 4
    if tok == 1:  # BEGIN_NODE
        end = d.find(b"\x00", p)
        nm = d[p:end].decode("ascii", "replace")
        print("  " * depth + f"[{nm}]")
        depth += 1
        p = (end + 4) & ~3
    elif tok == 2:
        depth = max(0, depth - 1)
    elif tok == 3:  # PROP
        ln, noff = struct.unpack(">II", d[p:p + 8])
        p += 8
        val = d[p:p + ln]
        p = (p + ln + 3) & ~3
        nm = name_of(noff)
        if ln == 0:
            vs = ""
        elif all(32 <= b < 127 or b == 0 for b in val) and ln > 1:
            vs = repr(val.rstrip(b"\x00"))
        else:
            ints = [f"{x:#x}" for x in struct.unpack(f">{ln//4}I", val[:ln // 4 * 4])]
            vs = " ".join(ints) + (f"  hex={val.hex()}" if ln <= 32 else "")
        print("  " * depth + f"{nm} = {vs}")
    elif tok == 4:
        continue
    elif tok == 9:
        print("END")
        break
    else:
        print(f"unknown token {tok} at {p-4:#x}")
        break
