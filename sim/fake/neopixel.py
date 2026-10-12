import simstate as state


class NeoPixel:
    ORDER = (1, 0, 2, 3)

    def __init__(self, pin, n, bpp=3, timing=1):
        self.n = n
        self.buf = [(0, 0, 0)] * n

    def __len__(self):
        return self.n

    def __setitem__(self, i, v):
        self.buf[i] = tuple(v[:3])

    def __getitem__(self, i):
        return self.buf[i]

    def fill(self, v):
        self.buf = [tuple(v[:3])] * self.n

    def write(self):
        state.leds = list(self.buf)
