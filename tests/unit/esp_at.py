"""Simulator of the IoT:bit Wi-Fi module (AT 1.4.1, bl_iot_sdk 1.6.36) for unit tests.

It replaces the micro:bit UART and clock. Answers, delays and chunking follow the
recording in data/esp_at_recording.txt; test_esp_at.py replays that recording.
Answers marked ASSUMED were not seen on the real module.
"""

import re

OK = b"\r\nOK\r\n"
ERROR = b"\r\nERROR\r\n"
MAC = "aa:bb:cc:dd:ee:ff"
_VERSION = (
    b"AT version:1.4.1\r\nSDK version:release_bl_iot_sdk_1.6.36\r\n"
    b"compile_time:Nov  1 2022 17:43:%s\r\nBin version:V4.18_P1.5.1-ca22907\r\n"
)
_BOOT = b"#" * 48 + b"\r\n" + _VERSION % b"23" + b"#" * 16 + b"\r\n\r\nready\r\n"


def args(text):
    """Split AT arguments: 0,"a,b",1 -> ['0', 'a,b', '1']; \\ escapes inside quotes."""
    found = re.findall(r'"((?:[^"\\]|\\.)*)"|([^,]+)', text)
    return [re.sub(r"\\(.)", r"\1", q) if q or not p else p for q, p in found]


def topic_matches(pattern, topic):
    p, t = pattern.split("/"), topic.split("/")
    for i, part in enumerate(p):
        if part == "#":
            return True
        if i >= len(t) or part not in ("+", t[i]):
            return False
    return len(p) == len(t)


class EspAt:
    def __init__(self, networks=None, servers=None, brokers=("test.mosquitto.org",),
                 ip="192.168.1.50", bssid=MAC, chunk=20):  # fmt: skip
        self.networks = dict(networks or {})  # ssid -> password
        self.servers = dict(servers or {})  # host -> function(request bytes) -> response bytes
        self.brokers = set(brokers)
        self.ip = ip
        self.bssid = bssid
        self.chunk = chunk  # bytes per UART chunk, one chunk every 2 ms
        self.now = 0  # ms
        self.echo = True  # on after power-up and after deep sleep
        self.saved = None  # last joined network; the module reconnects to it by itself
        self.received = []  # commands as the module received them
        self.published = []  # (topic, data) sent with AT+MQTTPUB
        self.answered = b""  # everything the micro:bit has read from the module
        self._wifi = None  # (ssid, time when connected)
        self._tcp = None
        self._mqtt = None
        self._subs = []
        self._out = []  # (time, bytes) waiting in the UART
        self._tail = 0  # time when the UART is free again
        self._buf = b""
        self._raw = 0  # bytes expected after AT+CIPSEND
        self._busy = 0
        self._awake = 0
        self._mute = []
        self._inject = []

    # micro:bit side: uart.init/read/write, sleep, ticks_ms

    def init(self, *args, **kwargs):
        pass

    def read(self):
        ready = b"".join(d for t, d in self._out if t <= self.now)
        self._out = [(t, d) for t, d in self._out if t > self.now]
        self.answered += ready
        return ready or None

    def write(self, data):
        if isinstance(data, str):
            data = data.encode()
        if self.now < self._awake:
            return  # deep sleep: the module does not listen
        self._buf += data
        while True:
            if self._raw:
                if len(self._buf) < self._raw:
                    return
                payload, self._buf = self._buf[: self._raw], self._buf[self._raw :]
                self._raw = 0
                self._payload(payload)
                continue
            i = self._buf.find(b"\r\n")
            if i < 0:
                return
            line, self._buf = self._buf[:i], self._buf[i + 2 :]
            self._command(line)

    def sleep(self, ms):
        self.now += ms

    def ticks_ms(self):
        return self.now

    # test side: faults and events

    def mute(self, prefix):
        """Commands starting with prefix get no answer (module hangs)."""
        self._mute.append(prefix)

    def inject(self, line, during):
        """Send line (an unsolicited message) inside the answer to the next command `during`."""
        self._inject.append((during, line.encode() + b"\r\n"))

    def push(self, line, delay=0):
        """Send an unsolicited line now (or after delay ms), e.g. a message from the broker."""
        self._schedule(self.now + delay, [(0, line.encode() + b"\r\n")])

    def deliver(self, topic, data):
        """A message from the broker arrives on a subscribed topic."""
        if any(topic_matches(s, topic) for s in self._subs):
            self.push('+MQTTSUBRECV:0,"%s",%d,%s' % (topic, len(data), data))

    @property
    def connected(self):
        return self._wifi is not None and self.now >= self._wifi[1]

    # module side

    def _schedule(self, start, events):
        for offset, data in sorted(events, key=lambda event: event[0]):
            t = max(start + offset, self._tail)  # the UART sends one byte stream in order
            for i in range(0, len(data), self.chunk):
                self._out.append((t, data[i : i + self.chunk]))
                t += 2
            self._tail = t
        if events:
            self._busy = max(self._busy, start + max(offset for offset, _ in events))

    def _command(self, line):
        start = max(self.now, self._busy)
        cmd = line.decode()
        self.received.append(cmd)
        events = [(0, line + b"\r\n")] if self.echo else []
        if not any(cmd.startswith(p) for p in self._mute):
            answer = self._answer(cmd, start)
            for during, extra in list(self._inject):
                if cmd.startswith(during) and answer:
                    self._inject.remove((during, extra))
                    answer.insert(0, (max(answer[0][0] - 4, 0), extra))
            events += answer
        self._schedule(start, events)

    def _answer(self, cmd, start):
        name, _, rest = cmd.partition("=")
        a = args(rest) if rest else []
        online = self._wifi is not None and start >= self._wifi[1]
        if name == "AT":
            return [(5, OK)]
        if name in ("ATE0", "ATE1"):
            self.echo = name == "ATE1"
            return [(6, OK)]
        if name == "AT+GMR":
            return [(10, _VERSION % b"20" + OK)]
        if name == "AT+CWMODE":
            return [(13, OK)]
        if name == "AT+CWJAP?":
            if not online:
                return [(6, OK)]
            line = '+CWJAP:"%s","%s",1,-64,0,65535,0,0,0\r\n' % (self._wifi[0], self.bssid)
            return [(11, line.encode() + OK)]
        if name == "AT+CWJAP":
            return self._join(a[0], a[1], start, online)
        if name == "AT+CWQAP":
            self._wifi = self._mqtt = self._tcp = None
            return [(1014, b"WIFI DISCONNECT\r\n"), (1108, OK)] if online else [(6, OK)]
        if name == "AT+CIFSR":
            ip = self.ip if online else "0.0.0.0"
            text = '+CIFSR:STAIP,"%s"\r\n+CIFSR:STAMAC,"%s"\r\n' % (ip, MAC)
            return [(11, text.encode() + OK)]
        if name == "AT+CIPSTATUS":
            return [(7, b"STATUS:%d\r\n" % (2 if online else 5) + OK)]  # 5: ASSUMED
        if name == "AT+CIPSTART":
            if not online or a[1] not in self.servers:
                return [(16, ERROR)]  # ASSUMED for no Wi-Fi
            self._tcp = a[1]
            return [(139, b"CONNECT\r\n" + OK)]
        if name == "AT+CIPSEND":
            if self._tcp is None:
                return [(5, ERROR)]  # ASSUMED
            self._raw = int(a[0])
            return [(5, OK + b"\r\n>")]
        if name == "AT+CIPCLOSE":
            if self._tcp is None:
                return [(4, ERROR)]
            self._tcp = None
            return [(5, b"CLOSED\r\n" + OK)]  # ASSUMED
        if name == "AT+MQTTUSERCFG":
            return [(6, OK)]
        if name == "AT+MQTTCONN?":
            if self._mqtt is None:
                return [(8, b'+MQTTCONN:0,0,0,"","","",0\r\n' + OK)]  # ASSUMED
            return [(11, b'+MQTTCONN:0,4,1,"%s","%s","",1\r\n' % self._mqtt + OK)]
        if name == "AT+MQTTCONN":
            if not online or a[1] not in self.brokers:
                return [(5000, ERROR)]  # ASSUMED
            self._mqtt = (a[1].encode(), a[2].encode())
            return [(307, b'+MQTTCONNECTED:0,1,"%s","%s","",1\r\n' % self._mqtt), (366, OK)]
        if name == "AT+MQTTSUB":
            if self._mqtt is None:
                return [(5, ERROR)]  # ASSUMED
            self._subs.append(a[1])
            return [(49, OK)]
        if name == "AT+MQTTPUB":
            if self._mqtt is None:
                return [(5, ERROR)]  # ASSUMED
            topic, data = a[1], a[2]
            self.published.append((topic, data))
            if any(topic_matches(s, topic) for s in self._subs):
                line = '+MQTTSUBRECV:0,"%s",%d,%s\r\n' % (topic, len(data), data)
                return [(41, line.encode()), (48, OK)]
            return [(41, OK)]
        if name == "AT+MQTTCLEAN":
            self._mqtt = None
            self._subs = []
            return [(32, b"+MQTTDISCONNECTED:0\r\n" + OK)]
        if name == "AT+GSLP":
            return self._deep_sleep(int(a[0]), start)
        return [(6, b"ERROR\r\n")]

    def _join(self, ssid, password, start, online):
        events = [(1015, b"WIFI DISCONNECT\r\n")] if online else []
        self._wifi = self._mqtt = self._tcp = None
        if self.networks.get(ssid) != password:
            code = 2 if ssid in self.networks else 3  # 3: ASSUMED (network not found)
            return events + [(7199, b"+CWJAP:%d\r\n" % code + ERROR)]
        self._wifi = (ssid, start + 2766)
        self.saved = ssid
        return events + [(1881, b"WIFI CONNECTED\r\n"), (2766, b"WIFI GOT IP\r\n" + OK)]

    def _deep_sleep(self, ms, start):
        wake = 7 + ms
        self._awake = start + wake
        self.echo = True
        self._wifi = self._mqtt = self._tcp = None
        self._subs = []
        events = [(7, OK), (wake + 1000, _BOOT)]
        if self.saved:
            self._wifi = (self.saved, start + wake + 4720)
            events += [(wake + 2210, b"\r\nWI"), (wake + 4720, b"FI CONNECTED\r\nWIFI GOT IP\r\n")]
        return events

    def _payload(self, payload):
        start = max(self.now, self._busy)
        host, self._tcp = self._tcp, None
        response = self.servers[host](payload)
        events = [(5, b"\r\nRecv %d bytes\r\n\r\nSEND OK\r\n" % len(payload))]
        events.append((139, b"\r\n+IPD,%d:" % len(response) + response))
        events.append((259, b"\r\nCLOSED\r\n"))
        self._schedule(start, events)
