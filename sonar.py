"""Sonar:bit ultrasonic distance sensor (ELECFREAKS Smart Science IoT Kit)."""

from machine import time_pulse_us
from utime import sleep_us


def distance_cm(pin):
    """Return distance in cm (whole number), or None if no echo came back.

    pin: digital pin the Sonar:bit is connected to (trigger and echo share one pin).
    """
    pin.write_digital(0)
    sleep_us(2)
    pin.write_digital(1)  # 10 µs trigger pulse
    sleep_us(10)
    pin.write_digital(0)
    t = time_pulse_us(pin, 1, 25000)  # echo length in µs, negative on timeout
    return None if t < 0 else (t + 29) // 58  # sound travels there and back: 58 µs per cm
