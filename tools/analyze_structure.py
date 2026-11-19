from pathlib import Path
import json,struct,zlib,collections,math
R=Path(__file__).resolve().parent; O=R/'analysis'
s=json.loads((O/'firmware_summary.json').read_text())
lines=[]
def say(x):lines.append(str(x));print(x)
a=(R/'S5___V28.bin').read_bytes(); b=(R/'S5___V29.bin').read_bytes()
for name in ['S5___V28.bin','S5___V29.bin']:
 d=(R/name).read_bytes();say('\n'+name)
 for off in range(0,0x1000,16):
  row=d[off:off+16]
  if any(row):say(f'{off:08X} {row.hex(" ")} '+''.join(chr(x) if 32<=x<127 else '.' for x in row))
 # transitions between high-entropy regions and padding/plain sections
 bl=s[name]['entropy_blocks']; low=[x for x in bl if x['entropy']<7.8]
 say('64KiB blocks entropy <7.8: '+str(low))
 for pos in s[name]['magic_candidates_unvalidated'].get('gzip',[]):
  try:
   de=zlib.decompressobj(31); out=de.decompress(d[pos:],1048576)
   say(f'gzip candidate {pos:08X}: output={len(out)} eof={de.eof}, capped at 1MiB')
  except zlib.error as e:say(f'gzip candidate {pos:08X}: INVALID {e}')
 # repetition check over aligned 16-byte payload blocks, not padding
 counter=collections.Counter(d[i:i+16] for i in range(0x400,len(d)-15,16) if d[i:i+16] not in (b'\0'*16,b'\xff'*16))
 say('Most common nonpadding aligned 16-byte blocks: '+str([(x.hex(),n) for x,n in counter.most_common(8)]))
# Equal/different regions at coarse granularity
runs=[];start=0;prev=None
for i in range(0,len(a),4096):
 same=a[i:i+4096]==b[i:i+4096]
 if prev is not None and same!=prev:runs.append({'start':start,'end':i,'identical':prev});start=i
 prev=same
runs.append({'start':start,'end':len(a),'identical':prev})
say('\n4KiB block equality runs: '+str(runs))
say('different fraction '+str(s['comparison']['different_bytes']/len(a)))
# Lens section markers
l=(R/'400BV020.plf').read_bytes()
for marker in [b'LENS-',b'PSLF',b'CABRIOLET',b'Panasonic',b'FIN\0']:
 p=0; hits=[]
 while (p:=l.find(marker,p))>=0:hits.append(hex(p));p+=1
 say('lens '+repr(marker)+': '+str(hits))
for p in [0x48000,0x48100,0x48140,0x48180,0x48200,0x48240,0x48280,0x482c0,0x48300,0x48340]:
 say(f'lens {p:08X}: '+l[p:p+64].hex(' '))
(O/'structure_details.txt').write_text('\n'.join(lines),encoding='utf-8')
