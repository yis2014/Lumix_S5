import re

d = open(r'out\rootfs1\etc\menuxml\MC801_allmenu.xml', 'rb').read().decode('utf-8', 'replace')

# English titles only: take the first <language code="en"> block
en = {}
m = re.search(r'<language code="en"[^>]*>(.*?)</language>', d, re.S)
if m:
    for t in re.finditer(r'<title id="([^"]+)">([^<]*)</title>', m.group(1)):
        en[t.group(1)] = t.group(2)

i = d.find('<record_qmenu>')
j = d.find('</record_qmenu>')
seg = d[i:j]

# top-level: items whose func_type is present at the same level (heuristic: depth 1)
# simple approach: walk lines, track <group> depth
depth = 0
rows = []
for mm in re.finditer(r'<(/?)group>|<item id="([^"]+)"([^>]*)>', seg):
    if mm.group(1) == '/':
        depth -= 1
        continue
    if mm.group(1) == '' and mm.group(2) is None:
        depth += 1
        continue
    if mm.group(2):
        attrs = mm.group(3)
        title = re.search(r'title_id="([^"]+)"', attrs)
        ft = re.search(r'func_type="([^"]+)"', attrs)
        ct = re.search(r'cmd_type="([^"]+)"', attrs)
        if depth == 0:
            rows.append((mm.group(2), title.group(1) if title else '',
                         en.get(title.group(1), '??') if title else '',
                         ft.group(1) if ft else '', ct.group(1) if ct else ''))

print('record_qmenu top-level items: %d' % len(rows))
for r in rows:
    print('  %-38s %-28s %-24s %-18s %s' % r)
