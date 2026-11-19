"""DS1307 real-time clock on the ELECFREAKS IoT:bit board (I2C address 0x68).

The clock keeps time on its CR1220 battery, but it runs only when the IoT:bit
is powered or the battery is fitted, and it is stopped until the time is set.
"""
from microbit import i2c

_ADDR = 0x68


def _bcd(v):
    return v - 6 * (v >> 4)


def _to_bcd(v):
    return v + 6 * (v // 10)


def now():
    """Return (year, month, day, hour, minute, second), or None if the clock is stopped."""
    i2c.write(_ADDR, b"\x00")
    r = i2c.read(_ADDR, 7)
    if r[0] & 0x80:  # CH bit: clock halted (never set, or battery was removed)
        return None
    h = r[2]
    if h & 0x40:  # 12-hour mode: bit 5 = PM
        h = _bcd(h & 0x1F) % 12 + (12 if h & 0x20 else 0)
    else:
        h = _bcd(h & 0x3F)
    return (_bcd(r[6]) + 2000, _bcd(r[5] & 0x1F), _bcd(r[4] & 0x3F), h,
            _bcd(r[1] & 0x7F), _bcd(r[0] & 0x7F))


def set_time(year, month, day, hour, minute, second):
    """Set the time (24-hour mode) and start the clock."""
    i2c.write(_ADDR, bytes((0, _to_bcd(second), _to_bcd(minute), _to_bcd(hour), 1,
                            _to_bcd(day), _to_bcd(month), _to_bcd(year % 100))))


def clear():
    """Reset the clock to 2000-01-01 00:00:00 and start it."""
    set_time(2000, 1, 1, 0, 0, 0)


def value(index):
    """Return one item of now(): 0 year, 1 month, 2 day, 3 hour, 4 minute, 5 second.

    Returns None if the index is out of range or the clock is stopped.
    """
    t = now()
    return t[index] if t and 0 <= index < 6 else None
