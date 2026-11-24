import re

d = open(r'out\rootfs1\etc\menuxml\MC801_allmenu.xml', 'rb').read().decode('utf-8', 'replace')
i = d.find('<record_qmenu>')
j = d.find('</record_qmenu>')
seg = d[i:j]
print('qmenu len', len(seg))
for k in ['iso', 'title_iso', 'menu_item_id_iso']:
    print(k, seg.lower().count(k))
ids = re.findall(r'<item id="([^"]+)"', seg)
print('total item nodes:', len(ids))
rest = [x for x in ids if not x.startswith('menu_item_id_ph_sty_')]
print('non-ph_sty ids:', rest[:30])
