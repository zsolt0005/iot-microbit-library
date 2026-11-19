"""Wi-Fi for the Wi-Fi module on the ELECFREAKS IoT:bit (AT commands over UART).

The micro:bit has one UART. After the first call it is connected to the Wi-Fi module
(P8 TX, P12 RX), so print() over USB stops working until uart.init(115200) is called.
"""

from microbit import pin8, pin12, sleep, uart
from utime import ticks_diff, ticks_ms

_OK = (b"OK\r\n", b"ERROR", b"FAIL")
_ready = False


def wait(ends, timeout):
    """Read the module answer until one of ends appears or timeout (ms). Returns bytes."""
    buf = b""
    start = ticks_ms()
    while ticks_diff(ticks_ms(), start) < timeout:
        d = uart.read()
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
    uart.read()  # drop old data
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
