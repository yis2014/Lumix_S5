import subprocess, re, struct, sys

BASE = 0x87707000
D = open(r'out\plain\postboot3.bin', 'rb').read()

def disasm(addr, size=0x120):
    s = addr
    e = addr + size
    open(r'out\frag_x.bin', 'wb').write(D[s-BASE:e-BASE])
    subprocess.run(['node', 'js/disasm_linear.js', 'out/frag_x.bin', '%x' % addr,
                    'out/disasm_x.txt', 'thumb'], capture_output=True, text=True)
    return open('out/disasm_x.txt', encoding='utf-8', errors='replace').read().splitlines()

def read_str(addr, n=48):
    if not (BASE <= addr < BASE + len(D)):
        return None
    o = addr - BASE
    raw = D[o:o+n]
    txt = ''.join(chr(b) if 32 <= b < 127 else '.' for b in raw)
    return txt if any(32 <= b < 127 for b in raw) else None

def analyze(name, addr, size=0x120):
    lines = disasm(addr, size)
    calls, refs = [], []
    for line in lines:
        m = re.match(r'([0-9a-f]+)\s+[0-9a-f]+\s+(\S+)\t(.*)', line)
        if not m:
            continue
        a = int(m.group(1), 16); mn = m.group(2); op = m.group(3)
        if mn in ('bl', 'blx') and '#0x' in op:
            t = int(op.split('#')[1], 16)
            if 0x868e5900 <= t <= 0x868e5a00:
                calls.append(t)
        if mn == 'adr':
            mm = re.search(r'#(-?0x[0-9a-f]+)', op)
            if mm:
                imm = int(mm.group(1), 16)
                pc = (a + 4) & ~3
                refs.append(('adr', pc + imm))
        if mn == 'ldr' and 'pc' in op:
            mm = re.search(r'#(-?0x[0-9a-f]+)', op)
            if mm:
                imm = int(mm.group(1), 16)
                pc = (a + 4) & ~3
                lit = pc + imm
                if BASE <= lit < BASE + len(D):
                    val = struct.unpack_from('<I', D, lit - BASE)[0]
                    if BASE <= val < BASE + len(D):
                        refs.append(('ldr', val))
    print('=== %s @0x%08X' % (name, addr))
    print('  syscalls:', ['0x%08X' % c for c in calls])
    for kind, t in refs:
        s = read_str(t)
        if s:
            print('  %s -> 0x%08X  "%s"' % (kind, t, s[:70].split('.')[0]))
    print()

TARGETS = [
    ('op0', 0x877AAD80), ('op1', 0x877AAD1A), ('op2', 0x877AACB2),
    ('op3', 0x877AAB12), ('op4', 0x877AAAA0), ('op5', 0x877AAA72),
    ('op6', 0x877AAA48), ('op7', 0x877AA8C2), ('op8', 0x877AA83A),
    ('op9@inline', 0x877AAE44), ('op10@inline', 0x877AAE5E), ('op11@inline', 0x877AAE6C),
]
for n, a in TARGETS:
    analyze(n, a)
