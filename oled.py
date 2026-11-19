"""SSD1306 OLED display 128x64 (ELECFREAKS Smart Science IoT Kit), I2C address 0x3C.

Text uses the built-in micro:bit 5x5 font: 25 characters per line, 8 lines.
No screen buffer is kept in RAM; text and clear write directly to the display.
"""
from microbit import Image, i2c

_ADDR = 0x3C
# Control byte 0x00 (commands follow), then the init sequence of the original library
# with two fixes: start line 0x40 (was 0x00) and page range 0-7 (was 0-63).
_INIT = (b"\x00\xae\xa4\xd5\xf0\xa8\x3f\xd3\x00\x40\x8d\x14\x20\x00\x21\x00\x7f"
         b"\x22\x00\x07\xa1\xc8\xda\x12\x81\xcf\xd9\xf1\xdb\x40\xa6\xd6\x00\xaf")
_ZERO = b"\x40" + bytes(128)  # control byte 0x40 (data follows) + one empty page


def _window(col0, col1, page0, page1):
    i2c.write(_ADDR, bytes((0, 0x21, col0, col1, 0x22, page0, page1)))


def init():
    """Initialise the display. Call once after power-up."""
    i2c.write(_ADDR, _INIT)


def clear():
    """Clear the whole display."""
    _window(0, 127, 0, 7)
    for _ in range(8):
        i2c.write(_ADDR, _ZERO)


def text(x, y, s):
    """Write string s at character column x (0-24) and line y (0-7).

    Characters that do not fit on the line are cut off.
    """
    s = s[:25 - x]
    if not s:
        return
    buf = bytearray(1 + 5 * len(s))
    buf[0] = 0x40
    i = 1
    for ch in s:
        img = Image(ch)
        for c in range(5):
            col = 0
            for r in range(5):
                if img.get_pixel(c, r):
                    col |= 2 << r
            buf[i] = col
            i += 1
    _window(x * 5, x * 5 + 5 * len(s) - 1, y, y)
    i2c.write(_ADDR, buf)
