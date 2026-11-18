# IoT library for BBC micro:bit

MicroPython library for the BBC micro:bit V2 with the ELECFREAKS IoT:bit expansion board.

## Origin

This library is based on the MicroPython library for IoT:bit by Radoslav Tóth, created as
part of his bachelor's thesis *IoT technológie s BBC micro:bit programované v MicroPythone*
(Constantine the Philosopher University in Nitra, 2025).

- Original source: https://github.com/RadoslavCs/Microbit/tree/main/iot_library (commit `6417574`)
- The first commit of this library contains the original files unchanged, except for the default
  ThingSpeak API key and Wi-Fi credentials in `main.py`, which were replaced with placeholders.
- The original repository has no license. The code is modified and extended as part of a master's
  thesis at the same university, with the agreement of the thesis supervisor.

### Build
``` bash
uv run pyright && uv run mpy-cross main.py && uv run uflash main.py dist/
```
