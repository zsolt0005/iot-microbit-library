"""Water level sensor (ELECFREAKS Smart Science IoT Kit).

pin must be an analog pin: P0, P1, P2 (P3, P4, P10 only with display.off()).
"""

from micropython import const

_FULL = const(700)  # analog reading when the sensing area is fully submerged


def percent(pin):
    """Return water level in percent (0-100), rounded like MakeCode."""
    v = pin.read_analog()
    if v > _FULL:
        v = _FULL
    return (v * 100 + _FULL // 2) // _FULL


def cm(pin, depth_cm=4):
    """Return water level in centimetres; depth_cm is the length of the sensing area."""
    v = pin.read_analog()
    if v > _FULL:
        v = _FULL
    return v * depth_cm / _FULL
