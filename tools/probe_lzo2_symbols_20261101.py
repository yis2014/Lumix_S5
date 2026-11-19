"""Probe available lzo2 DLL symbols without executing firmware or extraction."""
import ctypes,ctypes.util,json
from pathlib import Path
candidate=ctypes.util.find_library('lzo2')
if not candidate:raise SystemExit('LZO2_DLL_NOT_FOUND')
dll=ctypes.WinDLL(candidate)
symbols=['lzo1x_decompress_safe','__lzo_init_v2','lzo_version','lzo1x_1_compress','lzo_init']
out={'library':candidate,'symbols':{}}
for sym in symbols:
    try:obj=getattr(dll,sym);out['symbols'][sym]='present'
    except AttributeError:out['symbols'][sym]='absent'
print(json.dumps(out,indent=2))
