"""One session, one owner of serial. A stopped session cannot be rearmed."""
import json
import os
import socket
import threading
import time
from collections import deque
from pathlib import Path
from .protocol import Pose, Lines

class Bridge:
    def __init__(self, expected_game, session, status_file, log_file, serial_port='', serial_factory=None):
        self.expected_game, self.session = expected_game, session
        self.status_file, self.log_file = Path(status_file), Path(log_file)
        self.serial_port, self.serial_factory = serial_port, serial_factory
        self.serial = None
        self.sock = None
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.pose = None
        self.armed = False
        self.verified = False
        self.connected = False
        self.paused = False
        self.last_frame = None
        self.last_frame_at = 0.0
        self.last_tx_at = 0.0
        self.tx = 'None'
        self.rx = 'None'
        self.reason = 'Waiting for emulator'
        self.history = deque(maxlen=12)
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.log = self.log_file.open('a', encoding='utf-8', buffering=1)

    def record(self, kind, value):
        self.log.write(json.dumps({'time': time.time(), 'kind': kind, 'value': value}) + '\n')
        self.history.append(f'{kind}: {value}')

    def start(self):
        self.thread = threading.Thread(target=self.run, name='OpenMotionBridge', daemon=True)
        self.thread.start()

    def enable(self):
        with self.lock:
            if self.stop_event.is_set() or not self.verified or not self.pose or self.paused or time.monotonic()-self.last_frame_at > 0.5:
                raise RuntimeError('Wait for live, valid game outputs before enabling motion')
            if not self.serial_port:
                raise RuntimeError('Select the controller port in Setup')
            if self.serial is None:
                if self.serial_factory:
                    self.serial = self.serial_factory(self.serial_port, 115200)
                else:
                    import serial
                    device = serial.Serial(port=None, baudrate=115200, bytesize=8, parity='N', stopbits=1,
                                           timeout=0, write_timeout=0.1)
                    # Opening a Mega can still reset it on some USB adapters.
                    device.dtr = False
                    device.rts = False
                    device.port = self.serial_port
                    device.open()
                    self.serial = device
            try:
                self.write(b'MODESx')
                self.write(Pose().serial())
            except Exception:
                self.disconnect_serial()
                raise
            self.armed = True
            self.reason = 'Motion enabled; physical position unverified'
            self.record('motion', 'enabled')

    def write(self, packet):
        count = self.serial.write(packet)
        if count != len(packet):
            raise OSError('Incomplete serial write')
        self.tx = packet.decode('ascii')
        self.last_tx_at = time.monotonic()
        self.record('TX', self.tx)

    def disable(self, reason='Monitor only'):
        with self.lock:
            self.armed = False
            self.reason = reason
            if self.serial is not None:
                try:
                    self.write(Pose().serial())
                except Exception as e:
                    self.record('serial_error', str(e))
                    self.reason = f'{reason}; centre write failed'
                self.disconnect_serial()
            self.record('motion', self.reason)

    def disconnect_serial(self):
        if self.serial is not None:
            try:
                self.serial.close()
            finally:
                self.serial = None

    def handle(self, name, value):
        with self.lock:
            if name == 'mame_start':
                if value != self.expected_game:
                    raise ValueError('Unexpected emulator session: ' + value)
                self.connected = True
                self.reason = 'Monitor only'
            elif name == 'om_session':
                if abs(int(value)) != self.session:
                    raise ValueError('Session token mismatch')
                self.verified = True
            elif name == 'om_packet':
                try:
                    self.pose = Pose.unpack(int(value))
                except ValueError:
                    self.pose = None
                    self.disable('Invalid motion packet')
            elif name == 'om_frame':
                frame = int(value)
                if self.last_frame is not None and frame <= self.last_frame:
                    self.disable('Emulator restarted; enable motion again')
                self.last_frame, self.last_frame_at = frame, time.monotonic()
            elif name in ('om_paused', 'pause'):
                self.paused = bool(int(value))
                if self.paused:
                    self.disable('Paused; centred, motion disabled')
            elif name == 'mame_stop':
                self.disable('Game ended')
                self.stop_event.set()

    def tick(self, now=None):
        with self.lock:
            now = time.monotonic() if now is None else now
            if self.armed:
                if not self.connected or not self.verified or self.pose is None or self.paused or now-self.last_frame_at > 0.5:
                    self.disable('Game output lost; motion disabled')
                elif now-self.last_tx_at >= 0.05:
                    try:
                        self.write(self.pose.serial())
                    except Exception as e:
                        self.disable('Controller write failed: ' + str(e))
            if self.serial is not None:
                try:
                    data = self.serial.read(min(4096, self.serial.in_waiting))
                    if data:
                        self.rx = data.decode('utf-8', errors='replace').strip()[-250:]
                        self.record('RX', self.rx)
                except Exception as e:
                    self.disable('Controller read failed: ' + str(e))

    def status(self):
        with self.lock:
            pose = self.pose or Pose()
            return {'session': self.session, 'time': time.time(), 'armed': self.armed, 'connected': self.connected,
                    'verified': self.verified, 'pose': vars(pose), 'tx': self.tx, 'rx': self.rx,
                    'reason': self.reason, 'history': list(self.history)}

    def publish(self):
        status = self.status()
        # Lua reads this simple text file. No Lua is evaluated from host files.
        lines = [str(self.session), str(int(status['armed'])), str(time.time()),
                 status['tx'].replace('\n', ' '), status['rx'].replace('\n', ' '), status['reason']]
        tmp = self.status_file.with_suffix('.tmp')
        tmp.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        os.replace(tmp, self.status_file)

    def run(self):
        parser = Lines()
        try:
            deadline = time.monotonic()+45
            while not self.stop_event.is_set() and self.sock is None:
                try:
                    self.sock = socket.create_connection(('127.0.0.1',8000),timeout=0.1)
                    self.sock.settimeout(0.02)
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('No MAME output connection after 45 seconds')
                    self.stop_event.wait(0.1)
                self.publish()
            while not self.stop_event.is_set():
                try:
                    data = self.sock.recv(16384)
                    if not data:
                        break
                    for name, value in parser.feed(data):
                        self.handle(name, value)
                except socket.timeout:
                    pass
                self.tick()
                self.publish()
        except Exception as e:
            self.reason = str(e)
            self.record('error', str(e))
        finally:
            self.disable(self.reason if self.reason not in ('Monitor only',) else 'Game output disconnected')
            self.connected = self.verified = False
            if self.sock:
                self.sock.close()
            self.stop_event.set()
            self.publish()
            self.log.close()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1)
        else:
            self.disable('Closed')
            self.log.close()
