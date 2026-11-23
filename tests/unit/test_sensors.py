"""Sensor formulas compared with the MakeCode blocks for every possible ADC value."""

import itertools
import math

from conftest import FakePin

import dust
import noise
import pir
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
    assert sonar.distance_cm(pin) == -1
