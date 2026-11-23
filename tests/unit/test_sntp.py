"""sntp.py against the ESP-AT simulator; answers follow the SNTP recording of 23 Nov 2026."""

import time

from microbit import i2c

import sntp
import wifi


def internet_time(sim):
    """UTC that the simulated module reports at this moment."""
    return time.gmtime(sim.utc + sim.now // 1000)[:6]


def test_time_after_joining(sim):
    wifi.connect("Domov", "heslo")
    start = sim.now
    t = sntp.time()
    assert t == internet_time(sim)
    assert sim.now - start < 1000  # recorded: time after 0.5 s
    assert 'AT+CIPSNTPCFG=1,0,"pool.ntp.org","time.google.com"' in sim.received


def test_single_digit_day(sim):
    wifi.connect("Domov", "heslo")
    sim.utc = 1767225600 - sim.now // 1000  # 1 Jan 2026 00:00:00 UTC now: "Thu Jan 1 ..."
    assert sntp.time()[:3] == (2026, 1, 1)


def test_no_time_without_wifi(sim):
    assert sntp.time(timeout=5000) is None
    assert sim.now >= 5000
    assert sntp.sync(timeout=2000) is False


def test_sync_sets_the_rtc_in_utc(sim):
    wifi.connect("Domov", "heslo")
    sim.utc = 1795461709 - sim.now // 1000  # Mon 23 Nov 2026 19:21:49 UTC now
    assert sntp.sync() is True
    addr, data = i2c.writes[-1]
    assert addr == 0x68 and data[0] == 0  # written from the seconds register
    assert data[2:4] == bytes((0x21, 0x19))  # 19:21 in BCD
    assert data[5:8] == bytes((0x23, 0x11, 0x26))  # 23 Nov 2026


def test_sntp_is_off_again_after_restart(sim):
    wifi.connect("Domov", "heslo")
    assert sntp.time() is not None
    wifi.reset()  # recorded: after power-up AT+CIPSNTPCFG? is 0
    sim.sleep(3000)
    assert sntp.time() == internet_time(sim)  # time() turns SNTP on again
