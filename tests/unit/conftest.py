"""Run the library on a PC: replace micro:bit-only modules with small fakes.

Only logic is tested here (formulas, parsing). Hardware behaviour is checked on
the micro:bit itself.
"""

import os
import struct
import sys
import time
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.modules.pop("http", None)  # our http.py, not the CPython standard library package


class FakePin:
    def __init__(self, analog=0, digital=0):
        self.analog = analog  # int or iterator of ints
        self.digital = digital
        self.written = []

    def read_analog(self):
        return next(self.analog) if hasattr(self.analog, "__next__") else self.analog

    def read_digital(self):
        return self.digital

    def write_digital(self, v):
        self.written.append(v)

    def set_analog_period(self, ms):
        self.period = ms

    def write_analog(self, v):
        self.duty = v


class FakeI2C:
    def __init__(self):
        self.regs = {}  # (addr, reg) -> bytes returned by read after writing reg
        self.writes = []
        self._last = None

    def write(self, addr, data):
        self.writes.append((addr, bytes(data)))
        self._last = (addr, data[0])

    def read(self, addr, n):
        return self.regs.get(self._last, bytes(n))[:n]


class FakeUART:
    def __init__(self):
        self.rx = b""
        self.tx = []

    def init(self, *args, **kwargs):
        pass

    def read(self):
        d, self.rx = self.rx, b""
        return d or None

    def write(self, data):
        self.tx.append(data)


class FakeDisplay:
    def __init__(self):
        self.on = True
        self.shown = []

    def is_on(self):
        return self.on

    def show(self, image):
        self.shown.append(image)


microbit = types.ModuleType("microbit")
microbit.display = FakeDisplay()
microbit.i2c = FakeI2C()
microbit.uart = FakeUART()
microbit.sleep = lambda ms: None
microbit.pin8 = FakePin()
microbit.pin12 = FakePin()
microbit.Image = None
sys.modules["microbit"] = microbit

log = types.ModuleType("log")  # built-in data log of micro:bit V2
log.MILLISECONDS = 1
log.entries = []
log.full = False


def _log_add(**row):
    if log.full:
        raise OSError(28)
    log.entries.append(row)


log.add = _log_add
log.delete = lambda full=False: log.entries.clear()
log.set_labels = lambda *labels, timestamp=None: None
sys.modules["log"] = log

micropython = types.ModuleType("micropython")
micropython.const = lambda x: x
sys.modules["micropython"] = micropython

utime = types.ModuleType("utime")
utime.sleep_us = lambda us: None
utime.ticks_ms = lambda: int(time.monotonic() * 1000)
utime.ticks_diff = lambda a, b: a - b
sys.modules["utime"] = utime

machine = types.ModuleType("machine")
machine.time_pulse_us = lambda pin, level, timeout: pin.pulse
sys.modules["machine"] = machine

sys.modules["ustruct"] = struct


@pytest.fixture
def sim(monkeypatch):
    """The ESP-AT simulator in place of the UART and clock used by wifi.py and http.py."""
    from esp_at import EspAt

    import http
    import mqtt
    import wifi

    module = EspAt(networks={"Domov": "heslo"})
    monkeypatch.setattr(wifi, "uart", module)
    monkeypatch.setattr(wifi, "sleep", module.sleep)
    monkeypatch.setattr(wifi, "ticks_ms", module.ticks_ms)
    monkeypatch.setattr(wifi, "_ready", False)
    monkeypatch.setattr(wifi, "on_data", wifi._keep_all)
    monkeypatch.setattr(http, "uart", module)
    monkeypatch.setattr(mqtt, "uart", module)
    monkeypatch.setattr(mqtt, "sleep", module.sleep)
    for name, value in (("_messages", []), ("_partial", b""), ("_server", None),
                        ("_topics", []), ("dropped", 0)):  # fmt: skip
        monkeypatch.setattr(mqtt, name, value)
    return module
