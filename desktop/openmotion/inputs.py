"""Read both A-PAC gamepads on Windows without grabbing them from MAME.
MAME retains the game bindings; the launcher only polls while it has focus.
"""
import ctypes
import sys
import time

class JoyInfo(ctypes.Structure):
    _fields_=[(name,ctypes.c_uint32) for name in
              ['size','flags','x','y','z','r','u','v','buttons','button_number','pov','reserved1','reserved2']]

class Navigation:
    def __init__(self):
        self.last=0.0
        self.previous_buttons={}
        self.api=ctypes.windll.winmm if sys.platform=='win32' else None

    def poll(self):
        if not self.api:return None
        now=time.monotonic()
        for index in range(self.api.joyGetNumDevs()):
            info=JoyInfo();info.size=ctypes.sizeof(info);info.flags=0xff
            if self.api.joyGetPosEx(index,ctypes.byref(info))!=0:continue
            previous=self.previous_buttons.get(index,0)
            self.previous_buttons[index]=info.buttons
            if info.buttons & ~previous & 1:return 'Return'
            if info.buttons & ~previous & 2:return 'Escape'
            if now-self.last>0.22:
                if info.y<16384:self.last=now;return 'Up'
                if info.y>49152:self.last=now;return 'Down'
        return None
