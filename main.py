"""Start-up program: loads the configuration and shows "Ready" on the OLED display."""

import config  # noqa: F401 - Wi-Fi and ThingSpeak settings (copy config.example.py)
import oled

try:
    oled.init()
    oled.clear()
    oled.text(0, 0, "Ready")
except OSError:  # no display connected
    pass
