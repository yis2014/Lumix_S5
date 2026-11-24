import re, collections, sys

path = r'out\rootfs1\etc\menuxml\MC801_allmenu.xml'
d = open(path, 'rb').read().decode('utf-8', 'replace')

attrs = collections.Counter(re.findall(r'([a-zA-Z_]+)=', d))
print('attributes:', dict(attrs))
print('quick occurrences:', d.lower().count('quick'))
for m in list(re.finditer(r'<item[^>]*quick[^>]*>', d, re.I))[:5]:
    print('  ', m.group()[:200])

lits = re.findall(r'title="([^"]+)"', d)
print('literal title attrs:', len(lits), lits[:10])
print('title_id count:', len(re.findall(r'title_id=', d)))
print('cmd_type values:', sorted(set(re.findall(r'cmd_type="([^"]+)"', d)))[:40])
print('func_type count:', len(set(re.findall(r'func_type="([^"]+)"', d))))
