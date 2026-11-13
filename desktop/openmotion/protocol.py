"""MAME network framing and v55 serial protocol. No serial side effects here."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Pose:
    q: int = 16
    r: int = 16
    s: int = 2
    t: int = 2
    a: int = 0
    b: int = 0

    def __post_init__(self):
        for name, lo, hi in [('q',1,32),('r',1,32),('s',1,7),('t',1,7),('a',0,1),('b',0,1)]:
            value = getattr(self, name)
            if type(value) is not int or not lo <= value <= hi:
                raise ValueError(f'Invalid {name} value: {value}')

    @classmethod
    def unpack(cls, value):
        if value < 0 or value >= (1 << 22) or not (value & (1 << 20)):
            raise ValueError('Missing valid-frame bit or unknown packet bits')
        return cls(value & 63, (value >> 6) & 63, (value >> 12) & 7,
                   (value >> 15) & 7, (value >> 18) & 1, (value >> 19) & 1)

    def pack(self):
        return self.q | self.r << 6 | self.s << 12 | self.t << 15 | self.a << 18 | self.b << 19 | 1 << 20

    def serial(self, include_lamps=True):
        # Speeds precede new targets. Whole frame is one ordered serial write.
        packet=f'S{self.s}xT{self.t}xQ{self.q}xR{self.r}x'
        if include_lamps:packet+=f'A{self.a}xB{self.b}x'
        return packet.encode('ascii')

class Lines:
    """Consume CR, LF and CRLF across arbitrary TCP fragment boundaries."""
    def __init__(self):
        self.pending = bytearray()
        self.overlong = False

    def feed(self, data):
        result = []
        for byte in data:
            if byte in (10, 13):
                if self.pending and not self.overlong:
                    line = self.pending.decode('ascii', errors='replace')
                    if ' = ' in line:
                        name, value = line.split(' = ', 1)
                        result.append((name, value))
                self.pending.clear()
                self.overlong = False
            elif not self.overlong:
                self.pending.append(byte)
                if len(self.pending) > 1024:
                    self.pending.clear()
                    self.overlong = True
        return result
