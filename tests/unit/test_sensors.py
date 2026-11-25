"""Sensor formulas compared with the MakeCode blocks for every possible ADC value."""

import itertools
import math

from conftest import FakePin

import dust
import mq5
import noise
import pir
import relay
import servo
import soil
import sonar
import uv
import water


def js_round(x):  # Math.round in MakeCode (JavaScript): halves round up
    return math.floor(x + 0.5)


def test_pir():
    assert pir.detected(FakePin(digital=1)) is True
    assert pir.detected(FakePin(digital=0)) is False


def test_soil_matches_makecode():
    for v in range(1024):
        assert soil.moisture(FakePin(v)) == js_round(v * 100 / 1023), v


def test_water_matches_makecode_and_is_clamped():
    for v in range(1024):
        expected = min(js_round(v * 100 / 700), 100)
        assert water.percent(FakePin(v)) == expected, v
    assert water.cm(FakePin(350)) == 2.0
    assert water.cm(FakePin(1023)) == 4.0  # clamped to depth_cm


def test_dust_matches_makecode():
    for v in range(1024):
        d = (v * 4650 / 1023 - 380) * 5 / 29
        expected = js_round(d) if d > 0 else 0
        assert dust.density(FakePin(v), FakePin()) == expected, v


def test_dust_switches_led():
    led = FakePin()
    dust.density(FakePin(100), led)
    assert led.written == [0, 1]  # on (active low), then off


def test_noise_quiet_and_loud():
    assert noise.db(FakePin(500)) == 30  # no amplitude
    pin = FakePin(itertools.cycle((0, 100)))  # amplitude 100 -> 80 dB in MakeCode
    assert noise.db(pin, samples=100) == 80


def test_servo_pulse_width_and_clamp():
    pin = FakePin()
    for angle, duty in ((-5, 26), (0, 26), (45, 51), (90, 77), (135, 102), (180, 128), (200, 128)):
        servo.write(pin, angle)
        assert pin.period == 20
        assert pin.duty == duty, angle


def test_servo_home_moves_and_releases():
    pin = FakePin()
    servo.home(pin)
    assert pin.duty == 77
    assert pin.written == [0]


def test_uv_matches_original_and_is_clamped():
    for v in range(1024):
        original = ((v - 0) * (15 - 0)) / (625 - 0) + 0
        assert uv.intensity(FakePin(v)) == min(original, 15), v


def test_sonar():
    pin = FakePin()
    pin.pulse = 617  # echo of an object at ~10.6 cm
    assert sonar.distance_cm(pin) == 11
    pin.pulse = -1  # timeout, no echo
    assert sonar.distance_cm(pin) is None


def test_relay_set_on_off():
    pin = FakePin()
    relay.set(pin, True)
    relay.set(pin, False)
    relay.on(pin)
    relay.off(pin)
    assert pin.written == [1, 0, 1, 0]


def test_mq5_volts_through_divider():
    assert mq5.raw(FakePin(971)) == 971
    assert mq5.volts(FakePin(1023)) == 3.3 * 1.5
    assert abs(mq5.volts(FakePin(50), divider=1.5015) - 0.242) < 0.001  # clean air, measured


def test_mq5_without_power_is_none():
    for v in (0, 2, 5):
        assert mq5.volts(FakePin(v)) is None, v
        assert mq5.detect(FakePin(v)) is None, v
    assert mq5.volts(FakePin(6)) is not None


def test_mq5_detect_threshold():
    assert mq5.detect(FakePin(50)) is False  # 0.24 V, clean air
    assert mq5.detect(FakePin(310)) is True  # 1.5 V on AO
    assert mq5.detect(FakePin(309)) is False
    assert mq5.detect(FakePin(905), threshold=5.0) is False
