"""mqtt.py against the ESP-AT simulator; module behaviour from the tests in notes 7f."""

import mqtt
import wifi

BROKER = "test.mosquitto.org"


def online(sim, topic="domov/kotol"):
    assert wifi.connect("Domov", "heslo")
    assert mqtt.connect(BROKER, "kuchyna", "iot", 'pa"ss,word')
    assert mqtt.subscribe(topic)


def test_connect_uses_no_automatic_reconnect(sim):
    online(sim)
    cfg = next(c for c in sim.received if c.startswith("AT+MQTTUSERCFG"))
    assert cfg == r'AT+MQTTUSERCFG=0,1,"kuchyna","iot","pa\"ss\,word",0,0,""'
    assert sim.received[-2] == 'AT+MQTTCONN=0,"test.mosquitto.org",1883,0'
    assert mqtt.is_connected() is True


def test_connect_unknown_broker(sim):
    wifi.connect("Domov", "heslo")
    assert mqtt.connect("no-such-host.invalid", "kuchyna") is False


def test_publish_json_unchanged(sim):
    online(sim)
    data = mqtt.json({"t": 1795276800, "teplota": 21.5, "miesto": 'kuchyňa "A"', "rtc": None,
                      "alarm": False})  # fmt: skip
    assert data == '{"t":1795276800,"teplota":21.5,"miesto":"kuchyňa \\"A\\"","alarm":false}'
    assert mqtt.publish("domov/kuchyna/meranie", data) is True
    assert sim.published[-1] == ("domov/kuchyna/meranie", data)


def test_publish_without_broker(sim):
    wifi.connect("Domov", "heslo")
    assert mqtt.publish("domov/x", "1") is False


def test_message_before_a_command_is_kept(sim):
    online(sim)
    sim.deliver("domov/kotol", "ON")
    sim.sleep(100)  # the message is waiting in the UART
    assert wifi.at("AT+CIPSTATUS").endswith(b"STATUS:2\r\n\r\nOK\r\n")
    assert mqtt.message() == ("domov/kotol", "ON")
    assert mqtt.message() is None


def test_message_inside_an_answer_is_kept(sim):
    online(sim)
    sim.inject('+MQTTSUBRECV:0,"domov/kotol",2,ON', during="AT+CIPSTATUS")
    r = wifi.at("AT+CIPSTATUS")
    assert b"MQTTSUBRECV" not in r and r.endswith(b"OK\r\n")
    assert mqtt.message() == ("domov/kotol", "ON")


def test_own_publish_comes_back(sim):
    online(sim)
    assert mqtt.publish("domov/kotol", "OFF") is True
    assert mqtt.message() == ("domov/kotol", "OFF")


def test_message_split_into_single_bytes(sim):
    online(sim)
    sim.chunk = 1
    sim.deliver("domov/kotol", '{"a":1,\r\n"b":"x,y"}')  # comma and CRLF inside data
    assert wifi.at("AT").endswith(b"OK\r\n")
    assert mqtt.message() == ("domov/kotol", '{"a":1,\r\n"b":"x,y"}')


def test_message_waits_for_its_rest():
    assert mqtt._take(b"\r\nOK\r\n+MQTTSUB") == b"\r\nOK\r\n"
    assert mqtt._take(b'RECV:0,"t",5,ab') == b""
    assert mqtt._take(b"cde\r\nSTATUS:2") == b"STATUS:2"
    assert mqtt._messages.pop() == ("t", "abcde")


def test_broken_message_is_skipped():
    assert mqtt._take(b'+MQTTSUBRECV:0,"t",x,ab\r\nOK\r\n') == b'0,"t",x,ab\r\nOK\r\n'
    assert mqtt._messages == []
    mqtt._take(b'+MQTTSUBRECV:0,"t",900,' + b"a" * 600)  # length lost: never completes
    assert mqtt._partial == b"" and mqtt._messages == []


def test_full_queue_drops_oldest(sim):
    online(sim)
    for i in range(10):
        sim.deliver("domov/kotol", str(i))
    sim.sleep(500)
    wifi.at("AT")
    assert mqtt.dropped == 2
    assert [m[1] for m in iter(mqtt.message, None)] == [str(i) for i in range(2, 10)]


def test_check_when_all_is_well(sim):
    online(sim)
    sent = len(sim.received)
    assert mqtt.check() is True
    assert not any(c.startswith("AT+MQTTCONN=") for c in sim.received[sent:])


def test_check_after_wifi_loss(sim):
    online(sim)
    wifi.disconnect()  # 4th test: +MQTTDISCONNECTED, state 3
    assert mqtt.check() is False  # no IP and no network given
    assert mqtt.check("Domov", "heslo") is True  # joins, connects and subscribes again
    assert sim.received[-1] == 'AT+MQTTSUB=0,"domov/kotol",1'
    sim.deliver("domov/kotol", "ON")
    sim.sleep(10)  # the message needs a few ms in the UART
    assert mqtt.message() == ("domov/kotol", "ON")


def test_automatic_reconnect_would_block_the_ip(sim):
    """Why reconnect=0: 3rd test, the module did not get an IP while reconnecting by itself."""
    wifi.connect("Domov", "heslo")
    wifi.at('AT+MQTTCONN=0,"test.mosquitto.org",1883,1', 5000)
    wifi.disconnect()
    assert wifi.connect("Domov", "heslo", timeout=40000) is False
    assert wifi.has_ip() is False


def test_check_after_the_module_hung(sim):
    online(sim)
    sim.lose_wifi_silently()  # 1st test: state stays 6, publishing hangs the module
    assert mqtt.publish("domov/x", "1") is False
    assert mqtt.check("Domov", "heslo") is False  # hung: no answer, AT+RST not heard
    sim.sleep(sim.hang_ms)  # ASSUMED in the simulator: the module answers again later
    assert mqtt.check("Domov", "heslo") is True
    assert mqtt.publish("domov/x", "2") is True


def test_check_restarts_a_silent_module(sim):
    online(sim)
    sim.mute("AT$")  # plain AT gets no answer, AT+RST still works
    assert mqtt.check() is True
    assert "AT+RST" in sim.received
    assert sim.received[-1] == 'AT+MQTTSUB=0,"domov/kotol",1'
    assert b"heslo" not in sim.answered  # echo was turned off again after the restart


def test_disconnect_forgets_topics(sim):
    online(sim)
    mqtt.disconnect()
    assert mqtt.is_connected() is False
    assert mqtt.check() is True and not any(
        c.startswith("AT+MQTTSUB") for c in sim.received[sim.received.index("AT+MQTTCLEAN=0") :]
    )
