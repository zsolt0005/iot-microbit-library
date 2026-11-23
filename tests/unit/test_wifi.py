"""wifi, http and thingspeak against the ESP-AT simulator (see esp_at.py)."""

import pytest

import http
import thingspeak
import wifi


def test_connect(sim):
    assert wifi.connect("Domov", "heslo") is True
    assert sim.received[:2] == ["ATE0", "AT+CWMODE=1"]  # echo off before the password is sent
    assert b"heslo" not in sim.answered
    assert 2766 <= sim.now < 3500
    assert wifi.is_connected() is True
    assert wifi.ip() == "192.168.1.50"


def test_connect_wrong_password_and_unknown_network(sim):
    assert wifi.connect("Domov", "zle") is False
    assert 7199 <= sim.now < 8000  # the module answers ERROR after 7.2 s
    assert wifi.connect("Iny", "heslo") is False
    assert wifi.is_connected() is False
    assert wifi.ip() == "0.0.0.0"  # the real module reports 0.0.0.0, not an empty answer


def test_connect_module_does_not_answer(sim):
    sim.mute("AT+CWJAP")
    assert wifi.connect("Domov", "heslo", timeout=20000) is False
    assert sim.now >= 20000


def test_answers_split_into_single_bytes(sim):
    sim.chunk = 1
    assert wifi.connect("Domov", "heslo") is True
    assert wifi.ip() == "192.168.1.50"


def test_disconnect(sim):
    wifi.connect("Domov", "heslo")
    wifi.disconnect()
    assert wifi.is_connected() is False


def http_server(sim, response):
    requests = []

    def handler(request):
        requests.append(request)
        return response

    sim.servers["example.com"] = handler
    return requests


def test_http_get(sim):
    requests = http_server(sim, b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n42")
    wifi.connect("Domov", "heslo")
    assert http.get("http://example.com/a?b=1") == (200, "42")
    assert requests[0].startswith(b"GET /a?b=1 HTTP/1.1\r\nHost: example.com\r\n")


def test_http_server_not_found(sim):
    wifi.connect("Domov", "heslo")
    assert http.get("http://example.com/") == (0, "")


@pytest.mark.xfail(strict=True, reason="http.py returns chunk sizes with the body (recording 7d)")
def test_http_get_chunked(sim):
    body = b'{"feeds":[]}'
    http_server(sim, b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
                b"%x\r\n%s\r\n0\r\n\r\n" % (len(body), body))  # fmt: skip
    wifi.connect("Domov", "heslo")
    assert http.get("http://example.com/") == (200, body.decode())


def test_thingspeak_send(sim):
    requests = []

    def server(request):
        requests.append(request)
        return b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n17"

    sim.servers["api.thingspeak.com"] = server
    wifi.connect("Domov", "heslo")
    assert thingspeak.send("KEY", 21.5, 48) == 17
    assert b"/update?api_key=KEY&field1=21.5&field2=48 " in requests[0]


def mqtt_subscribed(sim):
    wifi.connect("Domov", "heslo")
    wifi.at('AT+MQTTUSERCFG=0,1,"node","","",0,0,""')
    wifi.at('AT+MQTTCONN=0,"test.mosquitto.org",1883,1', 5000)
    wifi.at('AT+MQTTSUB=0,"domov/kotol",1')


def test_message_before_a_command_is_kept(sim):
    mqtt_subscribed(sim)
    sim.deliver("domov/kotol", "ON")
    sim.sleep(100)  # the message is waiting in the UART
    assert wifi.at("AT+CIPSTATUS").endswith(b"STATUS:2\r\n\r\nOK\r\n")
    assert wifi.next_message() == ("domov/kotol", "ON")
    assert wifi.next_message() is None


def test_message_inside_an_answer_is_kept(sim):
    mqtt_subscribed(sim)
    sim.inject('+MQTTSUBRECV:0,"domov/kotol",2,ON', during="AT+CIPSTATUS")
    r = wifi.at("AT+CIPSTATUS")
    assert b"MQTTSUBRECV" not in r and r.endswith(b"OK\r\n")
    assert wifi.next_message() == ("domov/kotol", "ON")


def test_own_publish_comes_back_before_ok(sim):
    mqtt_subscribed(sim)  # recorded: +MQTTSUBRECV arrives before OK of AT+MQTTPUB
    assert wifi.at('AT+MQTTPUB=0,"domov/kotol","OFF",1,0') == b"\r\nOK\r\n"
    assert wifi.next_message() == ("domov/kotol", "OFF")


def test_message_split_into_single_bytes(sim):
    mqtt_subscribed(sim)
    sim.chunk = 1
    sim.deliver("domov/kotol", '{"a":1,\r\n"b":"x,y"}')  # comma and CRLF inside data
    assert wifi.at("AT").endswith(b"OK\r\n")
    assert wifi.next_message() == ("domov/kotol", '{"a":1,\r\n"b":"x,y"}')


def test_message_waits_for_its_rest():
    assert wifi._take(b"\r\nOK\r\n+MQTTSUB") == b"\r\nOK\r\n"
    assert wifi._take(b'RECV:0,"t",5,ab') == b""
    assert wifi._take(b"cde\r\nSTATUS:2") == b"STATUS:2"
    assert wifi._messages.pop() == ("t", "abcde")


def test_broken_message_is_skipped():
    assert wifi._take(b'+MQTTSUBRECV:0,"t",x,ab\r\nOK\r\n') == b'0,"t",x,ab\r\nOK\r\n'
    assert wifi._messages == []
    wifi._take(b'+MQTTSUBRECV:0,"t",900,' + b"a" * 600)  # length lost: never completes
    assert wifi._partial == b"" and wifi._messages == []


def test_full_queue_drops_oldest(sim):
    mqtt_subscribed(sim)
    for i in range(10):
        sim.deliver("domov/kotol", str(i))
    sim.sleep(500)
    wifi.at("AT")
    assert wifi.dropped == 2
    assert [wifi.next_message()[1] for _ in range(8)] == [str(i) for i in range(2, 10)]


@pytest.mark.xfail(strict=True, reason="step 4.5: echo is on again after deep sleep")
def test_password_not_echoed_after_deep_sleep(sim):
    wifi.connect("Domov", "heslo")
    wifi.at("AT+GSLP=1000")
    sim.sleep(8000)
    wifi.connect("Domov", "heslo")
    assert b"heslo" not in sim.answered
