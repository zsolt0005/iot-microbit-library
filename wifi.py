"""Wi-Fi for the Wi-Fi module on the ELECFREAKS IoT:bit (AT commands over UART).

The micro:bit has one UART. After the first call it is connected to the Wi-Fi module
(P8 TX, P12 RX), so print() over USB stops working until uart.init(115200) is called.
"""

from microbit import pin8, pin12, sleep, uart
from micropython import const
from utime import ticks_diff, ticks_ms

_OK = (b"OK\r\n", b"ERROR", b"FAIL")
_MSG = b"+MQTTSUBRECV:"
_MAX_MESSAGES = const(8)
_MAX_PARTIAL = const(512)  # longer unfinished message is treated as broken
_ready = False
_messages = []  # (topic, data) received from the MQTT broker, oldest first
_partial = b""  # start of a message whose rest has not arrived yet
dropped = 0  # messages thrown away because the queue was full


def _take(buf):
    """Move complete broker messages from buf to the queue; return the rest of buf.

    A message is +MQTTSUBRECV:<id>,"<topic>",<len>,<data>; data has exactly len bytes.
    """
    global _partial, dropped
    buf = _partial + buf
    _partial = b""
    if b"+" not in buf:
        return buf  # most answers: nothing to look for
    out = b""
    while True:
        i = buf.find(_MSG)
        if i < 0:
            j = len(buf) - len(_MSG)
            j = buf.rfind(b"+", j if j > 0 else 0)  # only the end can hold a cut marker
            if j >= 0 and _MSG.startswith(buf[j:]):  # the marker itself may be cut
                _partial = buf[j:]
                return out + buf[:j]
            return out + buf
        out += buf[:i]
        q = buf.find(b'"', i)
        q2 = buf.find(b'"', q + 1) if q >= 0 else -1
        c = buf.find(b",", q2 + 2) if q2 >= 0 else -1
        try:
            end = c + 1 + int(buf[q2 + 2 : c]) if c >= 0 else -1
        except ValueError:
            end = 0  # bytes were lost in the UART
        if end < 0 or len(buf) < end:
            if len(buf) - i <= _MAX_PARTIAL:
                _partial = buf[i:]  # wait for the rest
                return out
            end = 0
        if end == 0:
            buf = buf[i + len(_MSG) :]  # broken message: skip its marker
            continue
        if len(_messages) >= _MAX_MESSAGES:
            _messages.pop(0)
            dropped += 1
        _messages.append((buf[q + 1 : q2].decode(), buf[c + 1 : end].decode()))
        buf = buf[end + 2 :] if buf[end : end + 2] == b"\r\n" else buf[end:]


def _read():
    """Read the UART, keep broker messages, return the other bytes."""
    d = uart.read()
    return _take(d) if d else b""


def next_message():
    """Return the oldest message from the broker as (topic, data), or None."""
    _read()
    return _messages.pop(0) if _messages else None


def wait(ends, timeout):
    """Read the module answer until one of ends appears or timeout (ms). Returns bytes."""
    buf = b""
    start = ticks_ms()
    while ticks_diff(ticks_ms(), start) < timeout:
        d = _read()
        if d:
            buf += d
            for e in ends:
                if e in buf:
                    return buf
        else:
            sleep(1)
    return buf


def at(cmd, timeout=2000, ends=_OK):
    """Send an AT command and wait for OK/ERROR (or timeout). Returns the raw response bytes."""
    global _ready
    if not _ready:
        uart.init(115200, tx=pin8, rx=pin12)
        _ready = True
        sleep(100)
        uart.read()
        at("ATE0")  # no echo, so the Wi-Fi password is never sent back
    _read()  # drop old answers, keep broker messages
    uart.write(cmd + "\r\n")
    return wait(ends, timeout)


def connect(ssid, password, timeout=20000):
    """Connect to a Wi-Fi network. Returns True when connected."""
    at("AT+CWMODE=1")
    return b"OK\r\n" in at('AT+CWJAP="%s","%s"' % (ssid, password), timeout)


def is_connected():
    """Return True if the module is connected to a Wi-Fi network."""
    return b"+CWJAP:" in at("AT+CWJAP?")


def ip():
    """Return the IP address of the module as a string ("" if not connected)."""
    r = at("AT+CIFSR")
    i = r.find(b'STAIP,"')
    return r[i + 7 : r.find(b'"', i + 7)].decode() if i >= 0 else ""


def disconnect():
    """Disconnect from the Wi-Fi network."""
    at("AT+CWQAP")
