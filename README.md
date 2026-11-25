# IoT library for BBC micro:bit

MicroPython library for the **BBC micro:bit V2** with the **ELECFREAKS IoT:bit** expansion board
and the sensors of the ELECFREAKS Smart Science IoT Kit. It covers sensors, the display, time,
Wi-Fi, MQTT and HTTP. Every module is small, because the micro:bit has only ~20 kB for files.

- Firmware: official MicroPython for micro:bit **v2.1.2** (MicroPython 1.18) from
  [microbit-foundation/micropython-microbit-v2](https://github.com/microbit-foundation/micropython-microbit-v2/releases).
  Copy the `.hex` file to the `MICROBIT` drive.
- IoT:bit: power it over its own USB port (5 V). Its Wi-Fi module is an Ai-WB2-12F (AT commands
  over UART), its real-time clock a DS1307. I2C sensors use pins P19 (SCL) and P20 (SDA).

## Quick start

```bash
uv sync                          # Python tools for the PC
cp config.example.py config.py   # fill in Wi-Fi and MQTT; config.py is ignored by git
uv run python tools/upload.py    # upload main.py and what it imports
```

```python
# main.py
import config
import mqtt
import wifi
from bme680 import BME680

wifi.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
mqtt.connect(config.MQTT_HOST, "room", config.MQTT_USER, config.MQTT_PASSWORD)
t, p, h, gas = BME680(gas=False).read()
mqtt.publish("home/room/state", mqtt.json({"temp": t, "hum": h, "press": p}))
```

## Upload tool

`tools/upload.py` uploads a program as `main.py` (the file the micro:bit runs after start-up)
together with the local modules it imports, found in the code. Before uploading it deletes the
`.py` files the program does not need; other files (data written by the program) stay. Files are
minified (no comments and docstrings, one space per indent), which roughly halves their size.

```bash
uv run python tools/upload.py              # main.py and its imports
uv run python tools/upload.py bench.py     # bench.py as main.py and its imports
uv run python tools/upload.py --size       # only list the files and sizes
uv run python tools/upload.py --plain      # upload without minifying
```

## Sensors

Analog and digital sensors take the micro:bit pin they are connected to (`pin0`, `pin1`, ...).
Drivers raise `OSError` when a sensor does not answer and return `None` when a value is not valid
(see [guard](#guard)).

### BME680 / BME688

Temperature, pressure, humidity and gas resistance (I2C, address 0x76 or 0x77). Gas resistance
falls when the air gets worse; it is not an air quality index (that needs Bosch BSEC).

**Modes**
- with gas (default) – the heater warms the gas sensor before each measurement (~200 ms per read)
- `gas=False` – heater off, only temperature, pressure and humidity (~50 ms per read)

**Methods**
- `BME680(addr=None, heater_temp=320, heater_ms=150, gas=True)` – find the sensor (0x77, then
  0x76), read its calibration and set the heater (°C, ms)
- `read()` – one measurement: `(°C, Pa, %, gas Ω)`; gas is `None` without the heater or until it
  is stable; `None` for invalid values (settings are restored if the sensor was reset)

```python
from bme680 import BME680

s = BME680()                       # with gas
temp, press, hum, gas = s.read()   # gas is None until the heater is stable

s = BME680(gas=False)              # without gas
temp, press, hum, gas = s.read()   # gas is always None

s = BME680(heater_temp=300, heater_ms=100)   # own heater settings
```

### BME280

Temperature, pressure and humidity (I2C, address 0x76).

**Modes**
- `NORMAL` (default) – measures all the time; `read()` returns the latest result at once
- `FORCED` – measures only when asked and sleeps in between (lower power, slower `read()`)

**Methods**
- `BME280(mode=NORMAL, addr=0x76)` – check the chip, read its calibration and start it
- `read()` – one measurement: `(°C, Pa, %)`, or `None` if there is no valid result yet
- `temperature()`, `pressure()`, `humidity()` – one value from one measurement

```python
from bme280 import BME280, FORCED, NORMAL

s = BME280(mode=NORMAL)
temp, press, hum = s.read()

s = BME280(mode=FORCED)
temp, press, hum = s.read()        # starts one measurement and waits for it
print(s.temperature(), s.pressure(), s.humidity())
```

### PIR

Motion detector (digital).

**Methods**
- `detected(pin)` – `True` while the sensor detects motion

```python
import pir

if pir.detected(pin1):
    print("motion")
```

### Soil moisture

Soil moisture (analog).

**Methods**
- `moisture(pin)` – moisture in percent (0–100), rounded like MakeCode

```python
import soil

print(soil.moisture(pin1), "%")
```

### Water level

Water level (analog).

**Methods**
- `percent(pin)` – level in percent (0–100)
- `cm(pin, depth_cm=4)` – level in centimetres; `depth_cm` is the length of the sensing area

```python
import water

print(water.percent(pin1), "%", water.cm(pin1), "cm")
```

### Dust

Dust density (analog output, IR LED on a digital pin), same conversion as MakeCode.

**Methods**
- `density(out_pin, led_pin)` – dust density in µg/m³ (0 or more); `out_pin` must be an analog
  pin (P0, P1, P2; P3, P4, P10 only with `display.off()`)

```python
import dust

print(dust.density(pin1, pin2), "µg/m³")
```

### Sonar:bit

Ultrasonic distance sensor (trigger and echo on one pin).

**Methods**
- `distance_cm(pin)` – distance in whole centimetres, `None` when no echo comes back

```python
import sonar

d = sonar.distance_cm(pin1)
if d is not None:
    print(d, "cm")
```

### Noise

Sound level (analog), same algorithm as MakeCode.

**Methods**
- `db(pin, samples=250)` – sound level in dB (approximate, not calibrated); more samples give a
  steadier value but take longer

```python
import noise

print(noise.db(pin1), "dB")
```

### UV

UV intensity (analog).

**Methods**
- `intensity(pin)` – UV intensity from 0 to 15

```python
import uv

print(uv.intensity(pin1))
```

### MQ-5

Gas sensor module for LPG and natural gas (analog), powered from 5 V with a common ground.
AO gives up to 5 V, so connect it through a voltage divider: 10 kΩ from AO to the pin,
20 kΩ from the pin to GND (`divider` = (10 + 20) / 20 = 1.5). Do not connect DO (pulled up to
5 V). After power on the sensor needs a few minutes to settle, 24–48 h the first time.

**Methods**
- `raw(pin)` – raw ADC value (0–1023)
- `volts(pin, divider=1.5)` – voltage on AO, `None` when the sensor has no power
- `detect(pin, threshold=1.5, divider=1.5)` – `True` when AO reaches `threshold` volts,
  `None` when the value is not valid

```python
import mq5

print(mq5.volts(pin1), "V")            # ~0.25 V in clean air, ~4.5 V with gas
if mq5.detect(pin1, threshold=1.5):
    print("gas")
```

## Servo, relay and display

### Servo

Servo motor (PWM).

**Methods**
- `write(pin, angle)` – turn to an angle (0–180°) and hold it
- `release(pin)` – stop the pulses; the servo no longer holds its position
- `home(pin, angle=90, wait_ms=1000)` – move to the home angle, wait for the move, then release

```python
import servo

servo.write(pin1, 45)
servo.release(pin1)
servo.home(pin1)
```

### Relay

Relay module with a signal input (S), switched by a high level, powered from 5 V with a
common ground. Connect the device to COM and NO, so it is off when the relay is off.
The state cannot be read back from the pin, so the program keeps it.

**Methods**
- `set(pin, state)` – on (`True`, COM–NO closed) or off (`False`)
- `on(pin)` – switch on
- `off(pin)` – switch off; call it at start for a safe state

```python
import relay

relay.off(pin16)          # safe state at start
relay.set(pin16, True)
relay.on(pin16)
```

### OLED

SSD1306 display 128×64 (I2C, address 0x3C), 25 characters × 8 lines.

**Methods**
- `init()` – initialise the display; call once after power-up
- `clear()` – clear the whole display
- `text(x, y, s)` – write a string at character column `x` (0–24) and line `y` (0–7)

```python
import oled

oled.init()
oled.clear()
oled.text(0, 0, "Ready")
```

## Time

### RTC

DS1307 clock on the IoT:bit, kept in UTC. It stops when the power is off and no CR1220 battery is
fitted; without IoT:bit power it is not on I2C at all (`OSError(19)`).

**Methods**
- `now()` – `(year, month, day, hour, minute, second)`, or `None` while the clock is stopped
- `set_time(year, month, day, hour, minute, second)` – set the time and start the clock
- `unix()` – the time as a Unix timestamp, or `None` while stopped
- `value(index)` – one item of `now()`: 0 year, 1 month, 2 day, 3 hour, 4 minute, 5 second
- `clear()` – reset to 2000-01-01 00:00:00 and start the clock

```python
import rtc

rtc.set_time(2026, 11, 25, 18, 30, 0)
print(rtc.now())                   # (2026, 11, 25, 18, 30, 0)
print(rtc.unix())                  # 1795631400
print(rtc.value(3))                # 18
```

### SNTP

Internet time from the Wi-Fi module (needs Wi-Fi).

**Methods**
- `time(timeout=15000)` – UTC as `(year, month, day, hour, minute, second)`, or `None` without a
  time server
- `sync(timeout=15000)` – set the RTC from the internet; `True` on success

```python
import sntp

print(sntp.time())
sntp.sync()
```

## Network

### Wi-Fi

Wi-Fi module of the IoT:bit (AT commands over UART).

**Methods**
- `connect(ssid, password, timeout=20000)` – join a network; `True` when connected
- `is_connected()` – `True` while connected to a network
- `has_ip()` – `True` when the module has an IP address
- `ip()` – the IP address as a string (`""` when not connected)
- `disconnect()` – leave the network
- `reset(timeout=8000)` – restart the module; `True` when it is ready again
- `at(cmd, timeout=2000)` – send any AT command; returns the raw answer (bytes)

```python
import wifi

if wifi.connect("ssid", "password"):
    print(wifi.ip())
print(wifi.at("AT+GMR"))           # firmware version of the module
```

### MQTT

MQTT client over the Wi-Fi module (QoS 0/1, retained messages). Received messages wait in a queue
of 8; `mqtt.dropped` counts messages lost because it was full.

**Methods**
- `connect(host, client_id, user="", password="", port=1883)` – connect to the broker and
  subscribe again to earlier topics; `True` on success
- `subscribe(topic, qos=1)` – subscribe (wildcards `+` and `#` allowed)
- `publish(topic, data, qos=1, retain=False)` – publish a string; `True` when the module confirms
- `message()` – the oldest received message as `(topic, data)`, or `None`
- `json(values)` – a dict of numbers, strings and booleans as JSON (`None` values left out)
- `is_connected()` – `True` with an IP address and a broker connection
- `check(ssid=None, password=None)` – repair the connection if needed (restart the module, join
  Wi-Fi, connect to the broker); `True` when connected
- `disconnect()` – disconnect and forget the subscriptions

```python
import mqtt

mqtt.connect("192.168.1.10", "room", "user", "password")
mqtt.subscribe("home/room/config/#")

mqtt.publish("home/room/state", mqtt.json({"temp": 21.5}))         # QoS 1
mqtt.publish("home/room/state", mqtt.json({"temp": 21.5}), qos=0)  # no confirmation
mqtt.publish("home/room/status", "online", retain=True)           # kept for new subscribers

msg = mqtt.message()
if msg:
    topic, data = msg
mqtt.check("ssid", "password")
```

### HTTP

HTTP client over the Wi-Fi module (`http://` only, no HTTPS).

**Methods**
- `get(url, timeout=10000)` – GET; returns `(status, body)`, status 0 means no response
- `post(url, body, timeout=10000)` – POST with a JSON body (string)
- `request(method, url, body="", timeout=10000, limit=512)` – any method; the body is cut to
  `limit` bytes

```python
import http

status, body = http.get("http://example.com/")
status, body = http.post("http://example.com/api", '{"temp": 21.5}')
```

### ThingSpeak

ThingSpeak cloud over HTTP (free plan: one update per 15 s).

**Methods**
- `send(api_key, *values)` – write up to 8 values to fields 1–8 of a channel; returns the entry
  number, or 0 if the update was rejected

```python
import thingspeak

thingspeak.send("API_KEY", 21.5, 45)
```

## Utilities

### guard

Reads a sensor safely and remembers the error of each sensor, so a program reports only changes.
An `OSError` becomes `("unavailable", code)` (19 = not on I2C, 5 = transfer error), `None` becomes
`("invalid", 0)`.

**Methods**
- `read(name, fn)` – call `fn()` and return its value, or `None` on an error
- `active()` – sensors with a problem now: `{name: (error, code)}`
- `changes()` – changes since the last call, oldest first: `(name, error)`, error `None` = fixed

```python
import guard

data = guard.read("bme680", s.read)
dist = guard.read("sonar", lambda: sonar.distance_cm(pin1))
print(guard.active())              # {"bme680": ("unavailable", 19)}
for name, err in guard.changes():
    print(name, err)               # bme680 ('unavailable', 19), later bme680 None
```

### debug

Messages in the micro:bit V2 data log (open `MY_DATA.HTM` on the `MICROBIT` drive). A full log
never stops the program.

**Methods**
- `message(text)` – add a message; `False` if it cannot be written
- `error(text)` – add an error and show `E` if the display is on
- `clear()` – erase all messages (takes about 3.5 s)

```python
import debug

debug.message("started")
debug.error("no Wi-Fi")
```

## Development

```bash
uv run pytest                     # unit tests on the PC (fakes for micro:bit, simulated Wi-Fi module)
MQTT_USER=ci MQTT_PASSWORD=ci-test-only docker compose -f tests/integration/compose.yaml up -d --wait
MQTT_USER=ci MQTT_PASSWORD=ci-test-only uv run pytest tests/integration   # against Mosquitto
uv run ruff check . && uv run ruff format --check . && uv run pyright
```

GitHub Actions run the same checks, unit tests and integration tests for every push.

## Origin

This library is based on the MicroPython library for IoT:bit by Radoslav Tóth, created as
part of his bachelor's thesis *IoT technológie s BBC micro:bit programované v MicroPythone*
(Constantine the Philosopher University in Nitra, 2025).

- Original source: https://github.com/RadoslavCs/Microbit/tree/main/iot_library (commit `6417574`)
- The first commit of this library contains the original files unchanged, except for the default
  ThingSpeak API key and Wi-Fi credentials in `main.py`, which were replaced with placeholders.
- The original repository has no license. The code is modified and extended as part of a master's
  thesis at the same university, with the agreement of the thesis supervisor.
