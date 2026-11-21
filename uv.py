"""UV intensity sensor.

pin must be an analog pin: P0, P1, P2 (P3, P4, P10 only with display.off()).
"""

from micropython import const

_FULL = const(625)  # analog reading at the highest UV intensity (15)


def intensity(pin):
    """Return UV intensity from 0 to 15."""
    v = pin.read_analog()
    if v > _FULL:
        v = _FULL
    return v * 15 / _FULL
