"""Assemble a portable application from separately built components. No ROMs."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openmotion.storage import install_package

def assemble(app,emulator):
    app=Path(app)
    destination,manifest=install_package(emulator,app/'component-store')
    target=app/'emulator'
    if target.exists():raise ValueError('Portable emulator destination already exists')
    destination.rename(target)
    (app/'roms').mkdir(exist_ok=True)
    (app/'bundle.json').write_text(json.dumps({'schema':1,'cabinet':'G-LOC','emulator_version':manifest['version']},indent=2)+'\n',encoding='utf-8')
    (app/'START-HERE.txt').write_text('OPEN MOTION: G-LOC\n\nExtract the complete folder, then open OpenMotion.exe.\n\nMotion starts disabled. Choose a game and press Play.\nF6 changes the in-game command overlay. TAB opens MAME input setup.\nController serial: 115200 baud, 8N1. Select its port under Setup.\n\nPublic application packages contain ROM patches. Import your own complete ROM ZIPs.\nThe privately supplied test pack may already contain your converted sets.\n',encoding='utf-8')
    return app

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('application');p.add_argument('emulator');a=p.parse_args();print(assemble(a.application,a.emulator))
