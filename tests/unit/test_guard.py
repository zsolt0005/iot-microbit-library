"""guard.py: errors are remembered per sensor and reported only when they change."""

import pytest
from microbit import i2c
from test_bme680 import BME680, sensor

import guard


@pytest.fixture(autouse=True)
def clean():
    guard._active.clear()
    guard.changes()


def broken(code):
    def fn():
        raise OSError(code)

    return fn


def test_value_passes_through():
    assert guard.read("a", lambda: 21.5) == 21.5
    assert guard.read("a", lambda: 0) == 0  # 0 is a valid value, not an error
    assert guard.active() == {}
    assert guard.changes() == []


def test_error_and_recovery_are_reported_once():
    assert guard.read("bme680", broken(19)) is None
    assert guard.read("bme680", broken(19)) is None  # same error again: no new change
    assert guard.active() == {"bme680": ("unavailable", 19)}
    assert guard.changes() == [("bme680", ("unavailable", 19))]
    assert guard.changes() == []  # each change only once
    assert guard.read("bme680", lambda: (21.5, 101300, 45.0, None)) is not None
    assert guard.active() == {}
    assert guard.changes() == [("bme680", None)]


def test_none_is_invalid_and_other_error_is_a_change():
    guard.read("sonar", lambda: None)
    guard.read("sonar", broken(5))
    assert guard.changes() == [("sonar", ("invalid", 0)), ("sonar", ("unavailable", 5))]


def test_sensors_are_independent():
    guard.read("a", broken(19))
    guard.read("b", lambda: 1)
    guard.read("b", lambda: None)
    assert guard.active() == {"a": ("unavailable", 19), "b": ("invalid", 0)}


def test_oserror_without_code():
    guard.read("x", lambda: (_ for _ in ()).throw(OSError()))
    assert guard.active() == {"x": ("unavailable", 0)}


def test_bme680_disconnected_and_back(monkeypatch):
    s = sensor(BME680, 0)

    def no_device(*args):
        raise OSError(19)  # what the micro:bit raises when nothing answers on I2C

    with monkeypatch.context() as m:
        m.setattr(i2c, "write", no_device)
        assert guard.read("bme680", s.read) is None
    assert guard.read("bme680", s.read)[:3] == BME680["expected"][:3]
    assert guard.changes() == [("bme680", ("unavailable", 19)), ("bme680", None)]
