"""MQ-5 gas sensor module (LPG, natural gas), powered from 5 V.

The analog output AO gives up to 5 V, so it goes to an analog pin through a voltage
divider, e.g. 10 kOhm from AO to the pin and 20 kOhm from the pin to GND
(divider = (10 + 20) / 20 = 1.5). The digital output DO is not used: it is pulled up
to 5 V. The sensor needs a few minutes to warm up after power on (24-48 h the first time).

pin must be an analog pin: P0, P1, P2 (P3, P4, P10 only with display.off()).
"""

from micropython import const

_NO_POWER = const(5)  # a powered sensor gives at least ~0.2 V, the pin reads ~0 without power


def raw(pin):
    """Return the raw ADC value (0-1023) of the pin."""
    return pin.read_analog()


def volts(pin, divider=1.5):
    """Return the voltage on AO, or None when the sensor has no power."""
    v = pin.read_analog()
    if v <= _NO_POWER:
        return None
    return v * 3.3 / 1023 * divider


def detect(pin, threshold=1.5, divider=1.5):
    """Return True when the voltage on AO reaches threshold, None when it is not valid."""
    v = volts(pin, divider)
    return None if v is None else v >= threshold
