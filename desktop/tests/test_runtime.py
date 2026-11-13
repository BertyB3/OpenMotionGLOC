import hashlib
import json
import os
import socket
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from openmotion.protocol import Pose,Lines
from openmotion.bridge import Bridge
from openmotion.storage import install_package
from openmotion.roms import convert,patch_bytes

class Serial:
    def __init__(self,*args):self.packets=[];self.in_waiting=0;self.closed=False
    def write(self,data):self.packets.append(data);return len(data)
    def read(self,n):return b''
    def close(self):self.closed=True

class ProtocolTest(unittest.TestCase):
    def test_all_valid_positions_and_speeds(self):
        for q in range(1,33):
            for r in range(1,33):
                for speed in range(1,8):
                    p=Pose(q,r,speed,8-speed,1,0)
                    self.assertEqual(Pose.unpack(p.pack()),p)
                    self.assertEqual(Pose.unpack(p.pack() | 1<<21),p)
    def test_reject_bad_values(self):
        for value in [0,-1,1<<22,(1<<20)|63]:
            with self.assertRaises(ValueError):Pose.unpack(value)
        with self.assertRaises(ValueError):Pose(0,16)
        with self.assertRaises(ValueError):Pose(16,16,8,2)
    def test_fragments_and_overlong(self):
        p=Lines()
        self.assertEqual(p.feed(b'left_motor_posi'),[])
        self.assertEqual(p.feed(b'tion_nor = 16\r\nom_frame = 1\n'),[('left_motor_position_nor','16'),('om_frame','1')])
        self.assertEqual(p.feed(b'x'*1100+b'\rom_frame = 2\r'),[('om_frame','2')])

class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)
        self.serial=Serial()
        self.b=Bridge('gloc',123,self.path/'status.txt',self.path/'log.jsonl','COM7',lambda *a:self.serial)
    def tearDown(self):self.b.close();self.tmp.cleanup()
    def ready(self):
        self.b.handle('mame_start','gloc');self.b.handle('om_session','-123')
        self.b.handle('om_packet',str(Pose(10,22,3,4).pack()))
        self.b.handle('om_frame','1')
    def test_monitor_never_opens_serial(self):
        self.ready();self.b.tick();self.assertIsNone(self.b.serial);self.assertEqual(self.serial.packets,[])
    def test_enable_selects_serial_then_centre_then_pose(self):
        self.ready();self.b.enable();self.assertEqual(self.serial.packets[:2],[b'MODESx',Pose().serial()])
        self.b.tick(self.b.last_tx_at+0.06)
        self.assertEqual(self.serial.packets[-1],Pose(10,22,3,4).serial())
    def test_pause_centres_and_disarms(self):
        self.ready();self.b.enable();self.b.handle('om_paused','1')
        self.assertFalse(self.b.armed);self.assertTrue(self.serial.closed)
        self.assertEqual(self.serial.packets[-1],Pose().serial())
        self.b.handle('om_paused','0');self.assertFalse(self.b.armed)
    def test_stale_frames_disarm_without_replay(self):
        self.ready();self.b.enable();self.b.tick(self.b.last_frame_at+0.6)
        self.assertFalse(self.b.armed);self.assertEqual(self.serial.packets[-1],Pose().serial())
    def test_bad_packets_drop_old_pose(self):
        self.ready();self.b.enable();self.b.handle('om_packet','0')
        self.assertIsNone(self.b.pose);self.assertFalse(self.b.armed)
    def test_session_mismatch(self):
        with self.assertRaises(ValueError):self.b.handle('om_session','222')
        with self.assertRaises(ValueError):self.b.handle('mame_start','aburner2')
    def test_write_failure_disarms(self):
        self.ready();self.b.enable()
        self.serial.write=lambda data:0
        self.b.tick(self.b.last_tx_at+0.06);self.assertFalse(self.b.armed)
    def test_status_distinguishes_host_write_from_feedback(self):
        self.ready();self.b.publish()
        self.assertEqual((self.path/'status.txt').read_text().splitlines()[0],'123')
        self.assertEqual(self.b.status()['rx'],'None')

class UpdateTest(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def make(self,name='payload/emulator.exe',digest=None):
        data=b'not a real executable'
        manifest={'schema':1,'kind':'emulator','id':'test','version':'1.0','files':{name:digest or hashlib.sha256(data).hexdigest()}}
        archive=self.root/'update.zip'
        with zipfile.ZipFile(archive,'w') as z:z.writestr('manifest.json',json.dumps(manifest));z.writestr(name,data)
        return archive
    def test_settings_and_prior_versions_survive(self):
        cfg=self.root/'cabinet.json';cfg.write_text('keep settings')
        dest,_=install_package(self.make(),self.root)
        self.assertEqual((dest/'payload/emulator.exe').read_bytes(),b'not a real executable')
        self.assertEqual(cfg.read_text(),'keep settings')
        with self.assertRaises(ValueError):install_package(self.root/'update.zip',self.root)
    def test_zip_traversal_and_digest_rejected(self):
        with self.assertRaises(ValueError):install_package(self.make('payload/../../cabinet.json'),self.root)
        with self.assertRaises(ValueError):install_package(self.make(digest='bad'),self.root)

class PatchTest(unittest.TestCase):
    def test_preimage_and_overlapping_guards(self):
        with self.assertRaises(ValueError):patch_bytes(b'abc',[{'offset':1,'expected':'7a','replacement':'79'}])
        with self.assertRaises(ValueError):patch_bytes(b'abc',[{'offset':-1,'expected':'61','replacement':'62'}])
    def test_interleave_and_original_unchanged(self):
        import zlib
        crc=lambda b:f'{zlib.crc32(b):08x}'
        files={'even':b'ab','odd':b'cd','other':b'unchanged'}
        recipe={'chips':['even','odd'],'chip_size':2,'original_crc32':{'even':crc(b'ab'),'odd':crc(b'cd')},
                'patched_crc32':{'even':crc(b'xb'),'odd':crc(b'cd')},'patches':[{'offset':0,'expected':'61','replacement':'78'}]}
        out=convert(files,recipe);self.assertEqual(out['even'],b'xb');self.assertEqual(files['even'],b'ab')
        self.assertEqual(out['other'],b'unchanged');self.assertEqual(convert(out,recipe),out)

if __name__=='__main__':unittest.main()
