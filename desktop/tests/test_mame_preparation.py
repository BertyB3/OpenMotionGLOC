import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('prepare_mame',Path(__file__).resolve().parents[1]/'build/prepare_mame.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class PreparationTest(unittest.TestCase):
    def test_crlf_patch_on_lf_tarball_inside_parent_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            subprocess.run(['git','init','-q'],cwd=root,check=True)
            subprocess.run(['git','config','core.autocrlf','true'],cwd=root,check=True)
            upstream=root/'upstream';upstream.mkdir()
            source=upstream/'sample.txt';source.write_bytes(b'before\n')
            patch=root/'windows.patch'
            patch.write_bytes(b'--- a/sample.txt\r\n+++ b/sample.txt\r\n@@ -1 +1 @@\r\n-before\r\n+after\r\n')
            module.apply_patch(upstream,patch)
            self.assertEqual(source.read_bytes(),b'after\n')

if __name__=='__main__':unittest.main()

class CloneParentTest(unittest.TestCase):
    def test_clone_chain_is_checked_before_compiling(self):
        names=['gloc','strkfgtr','gforce2gloc','aburner2','sharrierglc','wingwar360']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'src/mame/sega';source.mkdir(parents=True)
            for name in ['segaybd.cpp','segaxbd.cpp','model1.cpp']:(source/name).write_text('')
            text='\n'.join('GAME(1985,'+n+',0,placeholder)' for n in names)
            text+='\nGAME(1985,sharrier,0,placeholder)\nGAME(1985,sharrier1,sharrier,placeholder)\n'
            path=source/'segahang.cpp'
            path.write_text(text+'GAME(1985,sharrier1glc,sharrier1,placeholder)\n')
            with self.assertRaises(ValueError):module.check_clone_parents(root)
            path.write_text(text+'GAME(1985,sharrier1glc,sharrier,placeholder)\n')
            module.check_clone_parents(root)
