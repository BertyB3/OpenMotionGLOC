"""Apply hash-guarded patches to pristine official MAME 0.276."""
import argparse
import hashlib
import json
import shutil
import subprocess
import re
from pathlib import Path

HERE=Path(__file__).resolve().parent

def apply_patch(root, patch):
    # Windows checkouts can convert patch files to CRLF while the verified
    # upstream tarball remains LF. Normalise only the patch transport bytes.
    payload=Path(patch).read_bytes().replace(b'\r\n',b'\n')
    for args in (['--check','-'], ['-']):
        subprocess.run(['git','-c','core.autocrlf=false','apply',*args],
                       cwd=root,input=payload,check=True)

def check_clone_parents(root):
    parents={}
    for name in ['segaybd.cpp','segaxbd.cpp','segahang.cpp','model1.cpp']:
        source=(Path(root)/'src/mame/sega'/name).read_text(encoding='utf-8')
        for game,parent in re.findall(r'^\s*GAME[L]?\(\s*[^,]+,\s*(\w+)\s*,\s*(\w+)',source,re.M):
            parents[game]=parent
    for game in ['gloc','strkfgtr','gforce2gloc','aburner2','sharrierglc','sharrier1glc','wingwar360']:
        if game not in parents:raise ValueError('Missing game registration: '+game)
        parent=parents[game]
        if parent!='0' and parents.get(parent)!='0':
            raise ValueError('MAME rejects a clone of a clone: '+game+' -> '+parent)

def prepare(root):
    root=Path(root)
    checks=json.loads((HERE/'upstream-files.json').read_text())
    for name,digest in checks.items():
        p=root/name
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
            raise ValueError('Not pristine MAME 0.276: '+name)
    for patch in sorted((HERE.parent/'patches').glob('*.patch')):
        apply_patch(root,patch)
    check_clone_parents(root)
    shutil.copyfile(HERE/'network.cpp',root/'src/osd/modules/output/network.cpp')
    print('Installed Open Motion desktop drivers and ordered loopback output transport.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mame',type=Path);a=p.parse_args();prepare(a.mame)
