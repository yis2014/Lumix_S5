"""Copy the demo program onto a mounted SD card as LUMIX.BIN.

Usage:
  python tools/prepare_sd.py G:\        # drive letter with the card mounted
"""
import os, shutil, sys, json

def main():
    if len(sys.argv) < 2:
        print(json.dumps({'ok': False, 'error': 'usage: prepare_sd.py <drive>'}))
        return 1
    drive = sys.argv[1]
    if not drive.endswith('\\') and not drive.endswith('/'):
        drive += '\\'
    if not os.path.isdir(drive):
        print(json.dumps({'ok': False, 'error': 'drive not found: ' + drive}))
        return 1
    src = os.path.join('payloads', 'LUMIX.BIN')
    if not os.path.isfile(src):
        print(json.dumps({'ok': False, 'error': 'payloads/LUMIX.BIN missing; build first'}))
        return 1
    dst = os.path.join(drive, 'LUMIX.BIN')
    shutil.copyfile(src, dst)
    same = open(src, 'rb').read() == open(dst, 'rb').read()
    print(json.dumps({'ok': same, 'target': dst, 'bytes': os.path.getsize(dst)}))
    return 0 if same else 1

if __name__ == '__main__':
    raise SystemExit(main())
