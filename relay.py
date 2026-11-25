"""Relay module with a signal input (S), switched by a high level.

pin can be any digital pin. Power the module from 5 V with a common ground.
The relay state cannot be read back: read_digital() would turn the pin into an input,
so the program keeps the state itself.
"""


def set(pin, state):
    """Switch the relay on (True, COM-NO closed) or off (False, COM-NC closed)."""
    pin.write_digital(1 if state else 0)


def on(pin):
    """Switch the relay on (COM-NO closed)."""
    set(pin, True)


def off(pin):
    """Switch the relay off (COM-NC closed); call it at start for a safe state."""
    set(pin, False)
