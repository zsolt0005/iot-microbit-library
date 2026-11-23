"""MQTT client over the Wi-Fi module (AT+MQTT* commands), using wifi.py.

The module never reconnects by itself (reconnect=0): with automatic reconnect it
could not get an IP address again after a Wi-Fi outage. check() restores the
connection instead.
"""

from microbit import sleep, uart
from micropython import const

import wifi

_MSG = b"+MQTTSUBRECV:"
_MAX_MESSAGES = const(8)
_MAX_PARTIAL = const(512)  # longer unfinished message is treated as broken
_messages = []  # (topic, data) received from the broker, oldest first
_partial = b""  # start of a message whose rest has not arrived yet
_server = None  # (host, client_id, user, password, port) of the last connect()
_topics = []  # (topic, qos) to subscribe again after a reconnect
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


def _q(s):
    """Escape a string for a quoted AT argument."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace(",", "\\,")


def connect(host, client_id, user="", password="", port=1883):
    """Connect to the broker and subscribe again to earlier topics. Returns True on success."""
    global _server
    _server = (host, client_id, user, password, port)
    wifi.on_data = _take
    cfg = 'AT+MQTTUSERCFG=0,1,"%s","%s","%s",0,0,""' % (_q(client_id), _q(user), _q(password))
    if b"OK\r\n" not in wifi.at(cfg):
        return False
    if b"OK\r\n" not in wifi.at('AT+MQTTCONN=0,"%s",%d,0' % (_q(host), port), 15000):
        return False
    for topic, qos in _topics:
        wifi.at('AT+MQTTSUB=0,"%s",%d' % (_q(topic), qos), 5000)
    return True


def subscribe(topic, qos=1):
    """Subscribe to topic (wildcards + and # allowed). Returns True on success."""
    if (topic, qos) not in _topics:
        _topics.append((topic, qos))
    return b"OK\r\n" in wifi.at('AT+MQTTSUB=0,"%s",%d' % (_q(topic), qos), 5000)


def publish(topic, data, qos=1, retain=False):
    """Publish data (str) without changing it. Returns True when the module confirms it."""
    data = data.encode()
    cmd = 'AT+MQTTPUBRAW=0,"%s",%d,%d,%d' % (_q(topic), len(data), qos, 1 if retain else 0)
    if b">" not in wifi.at(cmd, 2000, (b">", b"ERROR")):
        return False
    uart.write(data)
    return b"+MQTTPUB:OK" in wifi.wait((b"+MQTTPUB:OK", b"+MQTTPUB:FAIL", b"ERROR"), 5000)


def message():
    """Return the oldest message from the broker as (topic, data), or None."""
    wifi._read()
    return _messages.pop(0) if _messages else None


def json(values):
    """Return a dict of numbers, strings and booleans as JSON; None values are left out."""
    parts = []
    for key, v in values.items():
        if v is None:
            continue
        if isinstance(v, str):
            v = '"%s"' % v.replace("\\", "\\\\").replace('"', '\\"')
        elif isinstance(v, bool):
            v = "true" if v else "false"
        parts.append('"%s":%s' % (key, v))
    return "{" + ",".join(parts) + "}"


def is_connected():
    """Return True if the module has an IP address and a connection to the broker."""
    if not wifi.has_ip():
        return False
    r = wifi.at("AT+MQTTCONN?")
    i = r.find(b"+MQTTCONN:0,")
    return i >= 0 and r[i + 12 : i + 13] in (b"4", b"5", b"6")


def check(ssid=None, password=None):
    """Make sure the connection works; repair it if not. Returns True when connected.

    Order: module not answering -> AT+RST; no IP -> join ssid (if given);
    no broker -> connect again with the settings of the last connect().
    """
    if b"OK" not in wifi.at("AT", 500):
        if not wifi.reset():
            return False
        for _ in range(10):  # the module joins its last network by itself in ~3 s
            if wifi.has_ip():
                break
            sleep(500)
    if not wifi.has_ip() and not (ssid and wifi.connect(ssid, password)):
        return False
    if is_connected():
        return True
    return _server is not None and connect(*_server)


def disconnect():
    """Disconnect from the broker and forget the subscriptions."""
    del _topics[:]
    wifi.at("AT+MQTTCLEAN=0", 5000)
