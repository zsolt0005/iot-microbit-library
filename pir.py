"""PIR motion sensor (ELECFREAKS Smart Science IoT Kit)."""


def detected(pin):
    """Return True if the sensor on the given pin detects motion."""
    return pin.read_digital() == 1
