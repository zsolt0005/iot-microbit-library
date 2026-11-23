"""ESP-AT simulator whose AT+MQTT* commands use the real broker (paho-mqtt).

Everything else (UART, Wi-Fi, timing, chunking) comes from tests/unit/esp_at.py.
Network calls block in real time; the micro:bit clock of the simulator stays fake.
"""

import queue

import paho.mqtt.client as paho
from esp_at import ERROR, OK, EspAt, args

TIMEOUT = 5


class BridgedEspAt(EspAt):
    def __init__(self, broker, **kwargs):
        super().__init__(**kwargs)
        self.broker = broker  # real host and port; any host name in AT+MQTTCONN maps to it
        self._cfg = None  # (client_id, user, password) from AT+MQTTUSERCFG
        self._client = None
        self._inbox = queue.Queue()  # messages from the paho thread

    def read(self):
        while not self._inbox.empty():
            topic, data = self._inbox.get()
            line = b'+MQTTSUBRECV:0,"%s",%d,' % (topic.encode(), len(data)) + data + b"\r\n"
            self._schedule(self.now, [(0, line)])
        return super().read()

    def _answer(self, cmd, start):
        name, _, rest = cmd.partition("=")
        a = args(rest) if rest else []
        online = self._wifi is not None and start >= self._wifi[1]
        if name == "AT+MQTTUSERCFG":
            self._cfg = (a[2], a[3], a[4])
            return [(6, OK)]
        if name == "AT+MQTTCONN":
            return self._connect(online)
        if name == "AT+MQTTCONN?":
            state = 4 if self._client else 0
            return [(11, b'+MQTTCONN:0,%d,1,"broker","1883","",0\r\n' % state + OK)]
        if name == "AT+MQTTSUB":
            if self._client is None:
                return [(5, ERROR)]
            result, mid = self._client.subscribe(a[1], int(a[2]))
            return (
                [(49, OK)] if result == paho.MQTT_ERR_SUCCESS and self._acked(mid) else [(5, ERROR)]
            )
        if name == "AT+MQTTPUBRAW":
            if self._client is None:
                return [(204, ERROR)]
            self._raw, self._raw_topic = int(a[2]), (a[1], int(a[3]), a[4] == "1")
            return [(5, OK + b"\r\n>")]
        if name == "AT+MQTTCLEAN":
            self._close()
            return [(32, OK)]
        if name == "AT+CWQAP":
            events = super()._answer(cmd, start)
            if self._client:
                self._close()
                events.insert(-1, (1100, b"+MQTTDISCONNECTED:0\r\n"))
            return events
        return super()._answer(cmd, start)

    def _connect(self, online):
        if not online or self._cfg is None:
            return [(10200, ERROR)]
        self._close()
        client_id, user, password = self._cfg
        connected = queue.Queue()
        self._subacks = queue.Queue()
        client = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id=client_id,
                             protocol=paho.MQTTv311)  # fmt: skip
        if user:
            client.username_pw_set(user, password)
        client.on_connect = lambda c, u, f, code, p: connected.put(code)
        client.on_subscribe = lambda c, u, mid, codes, p: self._subacks.put(mid)
        client.on_message = lambda c, u, msg: self._inbox.put((msg.topic, msg.payload))
        client.connect(self.broker.host, self.broker.port, keepalive=30)
        client.loop_start()
        try:
            code = connected.get(timeout=TIMEOUT)
        except queue.Empty:
            code = None
        if code is None or code.is_failure:
            client.loop_stop()
            client.disconnect()
            return [(500, b"+MQTTDISCONNECTED:0\r\n" + ERROR)]  # ASSUMED for a refused login
        self._client = client
        return [(307, b'+MQTTCONNECTED:0,1,"broker","1883","",0\r\n'), (366, OK)]

    def _acked(self, mid):
        try:
            while self._subacks.get(timeout=TIMEOUT) != mid:
                pass
        except queue.Empty:
            return False
        return True

    def _mqtt_payload(self, payload):
        (topic, qos, retain), self._raw_topic = self._raw_topic, None
        info = self._client.publish(topic, payload, qos, retain)
        info.wait_for_publish(TIMEOUT)
        self.published.append((topic, payload.decode()))
        done = b"+MQTTPUB:OK\r\n" if info.is_published() else b"+MQTTPUB:FAIL\r\n"
        self._schedule(max(self.now, self._busy), [(48, done)])

    def _close(self):
        if self._client:
            self._client.disconnect()
            self._client.loop_stop()
            self._client = None
