"""User configuration survives application and emulator replacements."""
import json
import os
import shutil
import tempfile
import zipfile
import hashlib
import uuid
from pathlib import Path

ROOT = Path(os.environ.get('OPEN_MOTION_HOME') or (Path(os.environ.get('APPDATA', Path.home()/'.config'))/'OpenMotion'/'GLOC'))

def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    os.replace(tmp,path)

def load_config(bundle_root=None):
    p=ROOT/'cabinet.json'
    default={'emulator':'','rompath':str(ROOT/'roms'),'port':'','fullscreen':False,'overlay':True}
    if bundle_root is not None:
        bundle=Path(bundle_root)
        marker=bundle/'bundle.json'
        if marker.is_file() and json.loads(marker.read_text(encoding='utf-8')).get('schema')==1:
            if (bundle/'emulator/manifest.json').is_file():default['emulator']=str((bundle/'emulator').resolve())
            if (bundle/'roms').is_dir():default['rompath']=str((bundle/'roms').resolve())
    if p.exists():
        default.update(json.loads(p.read_text(encoding='utf-8')))
    return default

def install_package(archive, root=ROOT):
    """Offline packages are immutable, hash checked, and cannot replace settings."""
    root=Path(root)
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or len(names)>20000:
            raise ValueError('Duplicate or excessive package members')
        if sum(i.file_size for i in z.infolist())>1500*1024*1024:
            raise ValueError('Package exceeds 1.5 GB unpacked')
        manifest=json.loads(z.read('manifest.json'))
        if manifest.get('schema')!=1 or manifest.get('kind') not in ('emulator','rom_patch'):
            raise ValueError('Unsupported package type')
        for field in ('id','version'):
            text=manifest.get(field,'')
            if not text or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_' for c in text):
                raise ValueError('Invalid package '+field)
        expected=manifest.get('files')
        if not isinstance(expected,dict) or not expected or set(names)!={'manifest.json',*expected}:
            raise ValueError('Package file inventory mismatch')
        for name,digest in expected.items():
            parts=name.replace('\\','/').split('/')
            if not name.startswith('payload/') or any(x in ('','..','.') for x in parts) or ':' in name or '\\' in name:
                raise ValueError('Invalid package path')
            if hashlib.sha256(z.read(name)).hexdigest()!=digest:
                raise ValueError('Package checksum mismatch: '+name)
        destination=root/'packages'/manifest['kind']/manifest['id']/manifest['version']
        if destination.exists():
            raise ValueError('This version is already installed; existing installation preserved')
        destination.parent.mkdir(parents=True,exist_ok=True)
        stage=Path(tempfile.mkdtemp(prefix='.stage-',dir=destination.parent))
        try:
            for name in expected:
                target=stage/name
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(z.read(name))
            (stage/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
            os.replace(stage,destination)
        finally:
            if stage.exists():shutil.rmtree(stage)
    return destination,manifest
