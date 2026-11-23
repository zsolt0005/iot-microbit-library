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


def test_reset(sim):
    wifi.connect("Domov", "heslo")
    assert wifi.reset() is True
    assert sim.received[-2:] == ["AT+RST", "ATE0"]  # echo off again after the restart
    sim.sleep(2000)
    assert wifi.has_ip() is True  # joins the last network by itself


@pytest.mark.xfail(strict=True, reason="step 4.5: echo is on again after deep sleep")
def test_password_not_echoed_after_deep_sleep(sim):
    wifi.connect("Domov", "heslo")
    wifi.at("AT+GSLP=1000")
    sim.sleep(8000)
    wifi.connect("Domov", "heslo")
    assert b"heslo" not in sim.answered
