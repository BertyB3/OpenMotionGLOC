"""Apply frozen recipes locally; preserve source archives, reject unknown chips."""
import hashlib
import json
import os
import zipfile
import zlib
from pathlib import Path

def crc(data): return f'{zlib.crc32(data):08x}'

def read_zip(path):
    with zipfile.ZipFile(path) as z:
        infos=[i for i in z.infolist() if not i.is_dir()]
        if len(infos)>2000 or sum(i.file_size for i in infos)>256*1024*1024:
            raise ValueError('ROM archive too large')
        files={}
        for info in infos:
            name=info.filename.replace('\\','/').split('/')[-1].lower()
            if name in files:raise ValueError('Duplicate ROM chip name: '+name)
            files[name]=z.read(info)
        return files

def patch_bytes(data, patches):
    result=bytearray(data)
    used=set()
    for patch in patches:
        at=patch['offset']
        before=bytes.fromhex(patch['expected'])
        after=bytes.fromhex(patch.get('replacement',patch.get('replace','')))
        if len(before)!=len(after) or at<0 or at+len(before)>len(result):raise ValueError('Invalid patch range')
        if result[at:at+len(before)]!=before or used.intersection(range(at,at+len(before))):
            raise ValueError('ROM preimage or overlap check failed')
        used.update(range(at,at+len(before)))
        result[at:at+len(after)]=after
    return bytes(result)

def convert(files,recipe):
    files=dict(files)
    if 'targets' in recipe:  # Wing War's independent I/O and boot ROMs.
        for target in recipe['targets']:
            variants=target['variants']
            candidates=[n for n,b in files.items() if n in target['aliases'] or (len(b)==target['size'] and crc(b) in [v['crc32'] for v in variants]+[target['patchedCrc32']])]
            if len(candidates)!=1:raise ValueError('Include exactly one '+target['chip'])
            name=candidates[0];data=files.pop(name)
            if len(data)!=target['size']:raise ValueError('Wrong chip size')
            if crc(data)!=target['patchedCrc32']:
                variant=next((v for v in variants if v['crc32']==crc(data)),None)
                if variant is None:raise ValueError('Unknown ROM revision: '+name)
                data=patch_bytes(data,variant['patches'])
            if crc(data)!=target['patchedCrc32'] or hashlib.sha256(data).hexdigest()!=target['patchedSha256']:
                raise ValueError('Patched ROM digest failed')
            files[target['chip']]=data
    else:
        chips=recipe['chips']
        if any(n not in files for n in chips):raise ValueError('Missing program chips; use a complete game ZIP')
        checks={n:crc(files[n]) for n in chips}
        if checks==recipe['patched_crc32']:return files
        patches=recipe['patches']
        if checks!=recipe['original_crc32']:
            old=next((v for v in recipe.get('previous_versions',[]) if v['crc32']==checks),None)
            if old is None:raise ValueError('Unknown, mixed or partly patched program chips')
            patches=old['patches']
        size=recipe.get('chip_size',len(files[chips[0]]))
        if any(len(files[n])!=size for n in chips):raise ValueError('Wrong program chip size')
        image=bytearray(size*len(chips))
        for i,name in enumerate(chips):
            start=(i//2)*size*2+i%2
            image[start:start+size*2:2]=files[name]
        image=patch_bytes(image,patches)
        for i,name in enumerate(chips):
            start=(i//2)*size*2+i%2
            data=image[start:start+size*2:2]
            if crc(data)!=recipe['patched_crc32'][name]:raise ValueError('Patched ROM CRC failed')
            files[name]=data
    return files

def import_rom(source, destination, recipe_path=None):
    source,destination=Path(source),Path(destination)
    if source.resolve()==destination.resolve():raise ValueError('Choose an original outside the installed ROM folder')
    files=read_zip(source)
    if recipe_path:files=convert(files,json.loads(Path(recipe_path).read_text()))
    destination.parent.mkdir(parents=True,exist_ok=True)
    original=destination.parent/'originals'/source.name
    # Keep a content-addressed original so a same-named second import cannot replace it.
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    original=original.with_name(original.stem+'-'+digest[:12]+'.zip')
    original.parent.mkdir(parents=True,exist_ok=True)
    if not original.exists():original.write_bytes(source.read_bytes())
    temp=destination.with_suffix('.tmp')
    try:
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
            for name,data in files.items():z.writestr(name,data)
        os.replace(temp,destination)
    finally:temp.unlink(missing_ok=True)
    return destination
