"""Debug messages in the built-in micro:bit V2 data log.

Read them in MY_DATA.HTM on the MICROBIT drive. A full log never stops the program.
"""

import log
from microbit import display
from micropython import const

_MAX_TEXT = const(40)


def _labels():
    try:
        log.set_labels("msg", timestamp=log.MILLISECONDS)
    except OSError:
        pass


_labels()


def message(text):
    """Add text to the log; return False if it cannot be written."""
    try:
        log.add(msg=str(text)[:_MAX_TEXT])
    except OSError:
        return False
    return True


def error(text):
    """Log an error and show E if the display is on."""
    saved = message("ERR %s" % text)
    if display.is_on():
        display.show("E")
    return saved


def clear():
    """Erase all messages from flash (takes about 3.5 s)."""
    log.delete(full=True)
    _labels()
