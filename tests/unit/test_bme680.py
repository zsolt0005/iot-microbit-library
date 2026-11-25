"""BME680 / BME688 driver with calibration and raw data read from the real sensors on 24 Nov 2026.

Expected values come from the Pimoroni bme680 2.0.0 library (integer Bosch compensation)
for the same data; the driver gave identical results for 36 of 36 measurements on 6 sensors.
"""

import pytest
from microbit import i2c

import bme680

# sensor 1 (reports BME688) and sensor 2 (BME680): calibration 0x89 (25 B) + 0xE1 (16 B),
# registers 0x00, 0x02, 0x04 and one measurement from 0x1D (17 B)
BME688 = {
    "cal": bytes(
        [
            192,
            60,
            103,
            3,
            0,
            8,
            142,
            76,
            215,
            88,
            0,
            185,
            35,
            64,
            255,
            35,
            30,
            0,
            0,
            11,
            249,
            122,
            244,
            30,
            143,
            63,
            53,
            48,
            0,
            45,
            20,
            120,
            156,
            240,
            101,
            17,
            225,
            217,
            18,
            44,
            1,
        ]
    ),
    "other": (43, 22, 19),
    "raw": bytes([0, 0, 77, 188, 128, 126, 81, 0, 82, 234, 128, 0, 0, 0, 4, 255, 253]),
    "expected": (31.46, 101377, 46.053, 5684.846),
}
BME680 = {
    "cal": bytes([128, 19, 102, 3, 16, 128, 138, 18, 215, 88, 0, 84, 23, 89, 0, 19, 30, 0, 0,
                  86, 0, 123, 241, 30, 1, 65, 205, 33, 0, 45, 20, 120, 156, 210, 102, 47, 224,
                  192, 18, 58, 0]),
    "other": (33, 22, 227),
    "raw": bytes([0, 0, 93, 196, 240, 127, 208, 0, 60, 186, 128, 0, 0, 185, 251, 0, 4]),
    "expected": (31.89, 101278, 36.034, 3354.503),
}  # fmt: skip


def sensor(data, variant, addr=0x76, **kwargs):
    i2c.regs.clear()
    i2c.regs[(addr, 0xD0)] = b"\x61"
    i2c.regs[(addr, 0xF0)] = bytes((variant,))
    i2c.regs[(addr, 0x89)] = data["cal"][:25]
    i2c.regs[(addr, 0xE1)] = data["cal"][25:]
    for reg, value in zip((0x00, 0x02, 0x04), data["other"], strict=True):
        i2c.regs[(addr, reg)] = bytes((value,))
    # status 0x80 = new data; the recordings were read after read() had already cleared it
    i2c.regs[(addr, 0x1D)] = bytes((data["raw"][0] | 0x80,)) + data["raw"][1:]
    return bme680.BME680(**kwargs)


@pytest.mark.parametrize(("data", "variant"), [(BME688, 1), (BME680, 0)])
def test_matches_reference(data, variant):
    t, p, h, gas = sensor(data, variant).read()
    et, ep, eh, egas = data["expected"]
    assert (t, p, h) == (et, ep, eh)
    assert gas == pytest.approx(egas, abs=1e-3)


def test_variant_and_gas_register_layout():
    assert sensor(BME688, 1)._high is True
    assert sensor(BME680, 0)._high is False
    i2c.writes.clear()
    sensor(BME688, 1)
    assert (0x76, bytes((0x71, 0x20))) in i2c.writes  # BME688: run_gas is bit 5
    sensor(BME680, 0)
    assert (0x76, bytes((0x71, 0x10))) in i2c.writes  # BME680: run_gas is bit 4


def test_gas_none_until_heater_is_stable():
    data = dict(BME688, raw=BME688["raw"][:15] + bytes((95, 173)))  # first read after power-up
    assert sensor(data, 1).read()[3] is None


def test_address_0x77():
    assert sensor(BME680, 0, addr=0x77)._addr == 0x77


def test_wrong_chip_or_missing():
    i2c.regs.clear()
    i2c.regs[(0x76, 0xD0)] = b"\x60"  # BME280
    with pytest.raises(OSError):
        bme680.BME680()


def test_heater_settings():
    s = sensor(BME680, 0)
    assert s._heater_wait(150) == 101  # same codes as the reference library
    assert s._heater_wait(5000) == 0xFF
    assert 0 < s._heater_res(320, 25) < 256


@pytest.mark.parametrize(("data", "variant"), [(BME688, 1), (BME680, 0)])
def test_without_gas(data, variant):
    i2c.writes.clear()
    t, p, h, gas = sensor(data, variant, gas=False).read()
    assert (t, p, h) == data["expected"][:3]
    assert gas is None
    assert (0x76, bytes((0x71, 0))) in i2c.writes  # run_gas off
    assert not [w for w in i2c.writes if w[1][0] in (0x5A, 0x64)]  # heater not set


def test_without_gas_is_shorter(monkeypatch):
    waits = []
    monkeypatch.setattr(bme680, "sleep", waits.append)
    sensor(BME680, 0).read()
    sensor(BME680, 0, gas=False).read()
    assert waits == [200, 45]
