"""Servo motor (ELECFREAKS Smart Science IoT Kit).

pin can be any digital pin. Power the board through the IoT:bit USB port.
"""

from microbit import sleep
from micropython import const

_MIN = const(26)  # write_analog value for a 0.5 ms pulse (0 degrees) at a 20 ms period


def write(pin, angle):
    """Turn the servo to angle (0-180 degrees, clamped)."""
    if angle < 0:
        angle = 0
    elif angle > 180:
        angle = 180
    pin.set_analog_period(20)
    pin.write_analog(_MIN + angle * 17 // 30)


def release(pin):
    """Stop the pulses; the servo no longer holds its position."""
    pin.write_digital(0)


def home(pin, angle=90, wait_ms=1000):
    """Move to the home position from anywhere, wait for the move, then release."""
    write(pin, angle)
    sleep(wait_ms)
    release(pin)
