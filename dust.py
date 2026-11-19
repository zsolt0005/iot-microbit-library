"""Dust sensor (ELECFREAKS Smart Science IoT Kit), same conversion as MakeCode."""
from utime import sleep_us


def density(out_pin, led_pin):
    """Return dust density in µg/m³ (whole number, 0 or more).

    out_pin: analog pin of the sensor output (P0, P1, P2; P3, P4, P10 only with display.off()).
    led_pin: digital pin of the sensor IR LED.
    """
    led_pin.write_digital(0)  # IR LED on (active low)
    sleep_us(160)
    v = out_pin.read_analog()
    sleep_us(100)
    led_pin.write_digital(1)  # IR LED off
    # MakeCode: mV = v * 4650 / 1023 (3.1 V reference, 2:3 divider on the board),
    # dust = (mV - 380) * 5 / 29, rounded. Same result in integer math:
    d = (v * 23250 - 1928867) // 29667
    return d if d > 0 else 0
