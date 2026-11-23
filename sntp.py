"""Internet time (SNTP) from the Wi-Fi module and RTC sync, using wifi.py and rtc.py.

SNTP is off after every power-up of the module, so time() turns it on each call.
The RTC is kept in UTC.
"""

from microbit import sleep
from utime import ticks_diff, ticks_ms

import rtc
import wifi

_MONTHS = "JanFebMarAprMayJunJulAugSepOctNovDec"


def time(timeout=15000):
    """Return UTC as (year, month, day, hour, minute, second), or None without a time server."""
    if b"OK" not in wifi.at('AT+CIPSNTPCFG=1,0,"pool.ntp.org","time.google.com"'):
        return None
    start = ticks_ms()
    while ticks_diff(ticks_ms(), start) < timeout:
        r = wifi.at("AT+CIPSNTPTIME?")
        i = r.find(b"+CIPSNTPTIME:")
        p = r[i + 13 : r.find(b"\r", i)].split() if i >= 0 else []  # Mon Nov 23 19:21:49 2026
        if len(p) == 5 and p[4] != b"1970":
            month = _MONTHS.find(p[1].decode())
            hms = p[3].split(b":")
            if month >= 0 and len(hms) == 3:
                return (int(p[4]), month // 3 + 1, int(p[2]), int(hms[0]), int(hms[1]), int(hms[2]))
        sleep(500)
    return None


def sync(timeout=15000):
    """Set the RTC to UTC from the internet. Returns True on success."""
    t = time(timeout)
    if t is None:
        return False
    rtc.set_time(*t)
    return True
