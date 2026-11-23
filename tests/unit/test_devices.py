"""RTC, BME280, HTTP and ThingSpeak logic with fake I2C and a fake Wi-Fi module."""

import calendar

import log
from microbit import display, i2c

import bme280
import debug
import http
import rtc
import thingspeak
import wifi


def bcd(v):
    return (v // 10) << 4 | v % 10


def set_rtc(y, mo, d, h, mi, s, halted=False):
    i2c.regs[(0x68, 0)] = bytes(
        (bcd(s) | (0x80 if halted else 0), bcd(mi), bcd(h), 1, bcd(d), bcd(mo), bcd(y - 2000))
    )


def test_rtc_now_and_unix():
    set_rtc(2026, 11, 19, 18, 31, 9)
    assert rtc.now() == (2026, 11, 19, 18, 31, 9)
    assert rtc.value(5) == 9
    assert rtc.value(9) is None
    assert rtc.unix() == calendar.timegm((2026, 11, 19, 18, 31, 9, 0, 0, 0))


def test_rtc_halted_clock():
    set_rtc(2000, 1, 1, 0, 0, 0, halted=True)
    assert rtc.now() is None
    assert rtc.unix() is None


def test_rtc_unix_every_day_2000_2099():
    for y in range(2000, 2100):
        for mo in range(1, 13):
            for d in (1, 28):
                set_rtc(y, mo, d, 12, 0, 0)
                assert rtc.unix() == calendar.timegm((y, mo, d, 12, 0, 0, 0, 0, 0))


def test_rtc_set_time_writes_bcd():
    rtc.set_time(2026, 11, 19, 18, 31, 9)
    assert i2c.writes[-1] == (0x68, bytes((0, 0x09, 0x31, 0x18, 1, 0x19, 0x11, 0x26)))


# Calibration and raw data read from the kit's BME280 on 19 Nov 2026
CAL1 = bytes([12, 112, 229, 104, 50, 0, 72, 142, 226, 214, 208, 11, 71, 30, 220, 255,
              249, 255, 172, 38, 10, 216, 189, 16, 0, 75])  # fmt: skip
CAL2 = bytes([128, 1, 0, 16, 46, 3, 30])
RAW = bytes([85, 157, 144, 130, 91, 16, 99, 217])


def test_bme280_matches_bosch_reference():
    i2c.regs[(0x76, 0xD0)] = b"\x60"
    i2c.regs[(0x76, 0x88)] = CAL1
    i2c.regs[(0x76, 0xE1)] = CAL2
    i2c.regs[(0x76, 0xF7)] = RAW
    t, p, h = bme280.BME280().read()
    # Bosch floating-point reference for the same data: 24.009 °C, 98223.0 Pa, 48.341 %
    assert t == 24.01
    assert p == 98223
    assert abs(h - 48.341) < 0.01


def test_bme280_wrong_chip():
    i2c.regs[(0x76, 0xD0)] = b"\x61"  # BME680
    try:
        bme280.BME280()
    except OSError:
        return
    raise AssertionError("BME680 must not be accepted as BME280")


def test_debug_message_and_clear():
    debug.clear()
    assert debug.message("x" * 50) is True
    assert log.entries == [{"msg": "x" * 40}]
    debug.clear()
    assert log.entries == []


def test_debug_error_respects_display():
    debug.clear()
    display.shown.clear()
    display.on = False
    assert debug.error("mqtt fail") is True
    assert display.shown == []
    display.on = True
    debug.error("again")
    assert display.shown == ["E"]
    assert log.entries[0] == {"msg": "ERR mqtt fail"}


def test_debug_full_log_does_not_raise():
    log.full = True
    try:
        assert debug.message("x") is False
    finally:
        log.full = False


def fake_module(monkeypatch, answer):
    """Fake wifi.at/wifi.wait: CIPSTART and CIPSEND succeed, then the module sends answer."""
    sent = []

    def at(cmd, timeout=2000, ends=None):
        sent.append(cmd)
        return b">" if cmd.startswith("AT+CIPSEND") else b"CONNECT\r\n\r\nOK\r\n"

    monkeypatch.setattr(wifi, "at", at)
    monkeypatch.setattr(wifi, "wait", lambda ends, timeout: answer)
    return sent


def test_http_get_parses_ipd_blocks(monkeypatch):
    resp = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n42"
    answer = b"SEND OK\r\n+IPD,%d:%s\r\n+IPD,%d:%s\r\nCLOSED\r\n" % (
        20, resp[:20], len(resp) - 20, resp[20:])  # fmt: skip
    sent = fake_module(monkeypatch, answer)
    assert http.get("http://example.com:8080/a/b?c=1") == (200, "42")
    assert sent[0] == 'AT+CIPSTART="TCP","example.com",8080'


def test_http_errors(monkeypatch):
    fake_module(monkeypatch, b"")
    assert http.get("https://example.com/") == (0, "")  # https not supported
    assert http.get("http://example.com/") == (0, "")  # no answer


def test_thingspeak_send(monkeypatch):
    urls = []

    def get(url, timeout=10000):
        urls.append(url)
        return 200, "17"

    monkeypatch.setattr(http, "get", get)
    assert thingspeak.send("KEY", 1, 2.5) == 17
    assert urls[0] == "http://api.thingspeak.com/update?api_key=KEY&field1=1&field2=2.5"
    monkeypatch.setattr(http, "get", lambda url, timeout=10000: (200, "0"))
    assert thingspeak.send("KEY", 1) == 0  # rejected (rate limit)
