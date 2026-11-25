"""Guarded sensor reads: catch errors, remember the current error of each sensor.

Drivers report problems in one way: OSError = the sensor does not answer (e.g. 19 = not on I2C,
5 = transfer error), None = it answered, but the value is not valid. guard.read() turns both
into None for the caller and keeps the state, so a node reports only changes:

    data = guard.read("bme680", s.read)
    for name, err in guard.changes():
        ...  # err is ("unavailable", code), ("invalid", 0) or None (fixed again)
"""

_active = {}  # name -> (error, code) of sensors that have a problem now
_changed = []  # (name, error or None) not taken by changes() yet


def read(name, fn):
    """Call fn() and return its value, or None if it raised OSError or returned None."""
    try:
        v = fn()
        err = None if v is not None else ("invalid", 0)
    except OSError as e:
        v, err = None, ("unavailable", e.args[0] if e.args else 0)
    if _active.get(name) != err:
        if err:
            _active[name] = err
        else:
            del _active[name]
        _changed.append((name, err))
    return v


def active():
    """Sensors with a problem now: {name: (error, code)}."""
    return _active


def changes():
    """Changes since the last call, oldest first; each is returned only once."""
    global _changed
    c, _changed = _changed, []
    return c
