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
