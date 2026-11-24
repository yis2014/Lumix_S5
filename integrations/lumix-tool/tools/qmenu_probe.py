import re

d = open(r'out\rootfs1\etc\menuxml\MC801_allmenu.xml', 'rb').read().decode('utf-8', 'replace')
i = d.find('<record_qmenu>')
j = d.find('</record_qmenu>')
seg = d[i:j]

titles = {}
for m in re.finditer(r'<title id="([^"]+)">([^<]*)</title>', d):
    titles[m.group(1)] = m.group(2)

tops = re.findall(r'<item id="([^"]+)" title_id="([^"]+)" func_type="([^"]+)"', seg)
print('record_qmenu top-level items (%d):' % len(tops))
for t in tops:
    print('  %-40s %-32s %-14s -> %s' % (t[0], t[1], t[2], titles.get(t[1], '??')))

print()
print('--- first 12 item ids in document order inside record_qmenu ---')
for m in list(re.finditer(r'<item id="([^"]+)" title_id="([^"]+)"', seg))[:12]:
    print('  %-44s -> %s' % (m.group(1), titles.get(m.group(2), '??')))
