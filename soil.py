"""Soil moisture sensor (ELECFREAKS Smart Science IoT Kit)."""


def moisture(pin):
    """Return soil moisture in percent (0-100), rounded like MakeCode.

    pin must be an analog pin: P0, P1, P2 (P3, P4, P10 only with display.off()).
    """
    return (pin.read_analog() * 100 + 511) // 1023
