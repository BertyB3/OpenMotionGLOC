"""Create one independently installable, immutable offline update ZIP."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

def package(root,output,kind,version,executable=None):
    root=Path(root)
    payload={f'payload/{p.relative_to(root).as_posix()}':p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file()}
    manifest={'schema':1,'kind':kind,'id':'openmotion-mame' if kind=='emulator' else 'frozen-conversions',
              'version':version,'files':{n:hashlib.sha256(b).hexdigest() for n,b in payload.items()}}
    if kind=='emulator':
        manifest.update(driver_api='openmotion-0276-v1',executable=executable,
                        games=['gloc','strkfgtr','gforce2gloc','aburner2','sharrierglc','sharrier1glc','wingwar360'])
    else:manifest['requires']={'driver_api':'openmotion-0276-v1'}
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json',json.dumps(manifest,indent=2))
        for n,b in payload.items():z.writestr(n,b)
    print(output)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('kind',choices=['emulator','rom_patch']);p.add_argument('root');p.add_argument('output');p.add_argument('--version',required=True);p.add_argument('--executable');a=p.parse_args()
    if a.kind=='emulator' and not a.executable:p.error('--executable is required')
    package(a.root,a.output,a.kind,a.version,a.executable)
