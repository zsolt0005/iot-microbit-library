"""BME680 temperature, pressure, humidity and gas sensor (I2C, forced mode only).

Integer compensation from the Bosch BME680 API. Gas is returned as resistance in ohms:
it falls when the air gets worse. The air quality index (IAQ) needs Bosch BSEC,
which is not available for MicroPython. BME688 (same chip ID) is supported too.
"""

from microbit import i2c, sleep
from ustruct import unpack_from

# fmt: off
_K1 = (2147483647, 2147483647, 2147483647, 2147483647, 2147483647, 2126008810,
       2147483647, 2130303777, 2147483647, 2147483647, 2143188679, 2136746228,
       2147483647, 2126008810, 2147483647, 2147483647)
_K2 = (4096000000, 2048000000, 1024000000, 512000000, 255744255, 127110228, 64000000,
       32258064, 16016016, 8000000, 4000000, 2000000, 1000000, 500000, 250000, 125000)
# fmt: on


class BME680:
    def __init__(self, addr=None, heater_temp=320, heater_ms=150, gas=True):
        """Find the sensor (0x77 or 0x76 if addr is None), read calibration, set the heater.

        gas=False leaves the heater off: shorter measurement and gas is always None.
        """
        for a in (addr,) if addr else (0x77, 0x76):
            self._addr = a
            try:
                if self._reg(0xD0, 1)[0] == 0x61:
                    break
            except OSError:
                pass
        else:
            raise OSError("BME680 not found")
        self._high = self._reg(0xF0, 1)[0] == 1  # BME688
        c = self._reg(0x89, 25) + self._reg(0xE1, 16)
        self._t2, self._t3 = unpack_from("<hb", c, 1)
        self._p1, self._p2, self._p3 = unpack_from("<Hhb", c, 5)
        self._p4, self._p5, self._p7, self._p6 = unpack_from("<hhbb", c, 11)
        self._p8, self._p9, self._p10 = unpack_from("<hhB", c, 19)
        self._h2 = c[25] << 4 | c[26] >> 4
        self._h1 = c[27] << 4 | c[26] & 0x0F
        self._h3, self._h4, self._h5, self._h6, self._h7 = unpack_from("bbbBb", c, 28)
        self._t1, self._gh2, self._gh1, self._gh3 = unpack_from("<Hhbb", c, 33)
        self._range = (self._reg(0x02, 1)[0] & 0x30) >> 4
        self._heat_val = unpack_from("b", self._reg(0x00, 1))[0]
        self._sw_err = (self._reg(0x04, 1)[0] & 0xF0) >> 4
        self._gas_on = gas
        self._wait = heater_ms + 50 if gas else 45  # ms; T, P and H alone take ~42 ms
        self._t_fine = 0
        self._write(0x72, 0x01)  # humidity x1
        self._write(0x75, 0x00)  # no IIR filter
        if gas:
            self._write(0x5A, self._heater_res(heater_temp, 25))
            self._write(0x64, self._heater_wait(heater_ms))
        self._write(0x71, (0x20 if self._high else 0x10) if gas else 0)  # run gas, heater profile 0

    def _reg(self, reg, n):
        i2c.write(self._addr, bytes((reg,)))
        return i2c.read(self._addr, n)

    def _write(self, reg, value):
        i2c.write(self._addr, bytes((reg, value)))

    def read(self):
        """Measure once. Returns (°C, Pa, %, gas Ω); gas is None if the heater was not stable."""
        self._write(0x74, 0x54 | 1)  # temperature x2, pressure x16, forced mode
        sleep(self._wait)
        for _ in range(50):
            d = self._reg(0x1D, 17)
            if d[0] & 0x80:  # new data
                break
            sleep(10)
        else:
            raise OSError("BME680 measurement timeout")
        temp = self._temp(d[5] << 12 | d[6] << 4 | d[7] >> 4)
        press = self._press(d[2] << 12 | d[3] << 4 | d[4] >> 4)
        hum = self._hum(d[8] << 8 | d[9])
        g = d[15:17] if self._high else d[13:15]
        gas = None
        if self._gas_on and g[1] & 0x30 == 0x30:  # gas valid and heater stable
            gas = self._gas(g[0] << 2 | g[1] >> 6, g[1] & 0x0F)
        return temp / 100, press, hum / 1000, gas

    def _temp(self, adc):
        v1 = (adc >> 3) - (self._t1 << 1)
        v2 = (v1 * self._t2) >> 11
        v3 = ((((v1 >> 1) * (v1 >> 1)) >> 12) * (self._t3 << 4)) >> 14
        self._t_fine = v2 + v3
        return (self._t_fine * 5 + 128) >> 8

    def _press(self, adc):
        v1 = (self._t_fine >> 1) - 64000
        v2 = ((((v1 >> 2) * (v1 >> 2)) >> 11) * self._p6) >> 2
        v2 = v2 + ((v1 * self._p5) << 1)
        v2 = (v2 >> 2) + (self._p4 << 16)
        v1 = (((((v1 >> 2) * (v1 >> 2)) >> 13) * (self._p3 << 5)) >> 3) + ((self._p2 * v1) >> 1)
        v1 = ((32768 + (v1 >> 18)) * self._p1) >> 15
        p = ((1048576 - adc) - (v2 >> 12)) * 3125
        p = (p // v1) << 1 if p >= 1 << 31 else (p << 1) // v1
        v1 = (self._p9 * (((p >> 3) * (p >> 3)) >> 13)) >> 12
        v2 = ((p >> 2) * self._p8) >> 13
        v3 = ((p >> 8) * (p >> 8) * (p >> 8) * self._p10) >> 17
        return p + ((v1 + v2 + v3 + (self._p7 << 7)) >> 4)

    def _hum(self, adc):
        t = (self._t_fine * 5 + 128) >> 8
        v1 = (adc - self._h1 * 16) - (((t * self._h3) // 100) >> 1)
        v2 = (
            self._h2
            * (((t * self._h4) // 100) + (((t * ((t * self._h5) // 100)) >> 6) // 100) + 16384)
        ) >> 10
        v3 = v1 * v2
        v4 = ((self._h6 << 7) + ((t * self._h7) // 100)) >> 4
        v5 = ((v3 >> 14) * (v3 >> 14)) >> 10
        h = (((v3 + ((v4 * v5) >> 1)) >> 10) * 1000) >> 12
        return 0 if h < 0 else 100000 if h > 100000 else h

    def _gas(self, adc, rng):
        if self._high:
            return 1000000 * (262144 >> rng) / (4096 + 3 * (adc - 512))
        v1 = ((1340 + 5 * self._sw_err) * _K1[rng]) >> 16
        v2 = ((adc << 15) - 16777216) + v1
        r = (((_K2[rng] * v1) >> 9) + (v2 >> 1)) / v2
        return r + (1 << 32) if r < 0 else r

    def _heater_res(self, target, ambient):
        target = 200 if target < 200 else 400 if target > 400 else target
        v1 = ((ambient * self._gh3) / 1000) * 256
        v2 = (self._gh1 + 784) * (((((self._gh2 + 154009) * target * 5) / 100) + 3276800) / 10)
        v4 = (v1 + v2 / 2) / (self._range + 4)
        v5 = 131 * self._heat_val + 65536
        return int(((v4 / v5 - 250) * 34 + 50) / 100)

    @staticmethod
    def _heater_wait(ms):
        if ms >= 0xFC0:
            return 0xFF
        f = 0
        while ms > 0x3F:
            ms //= 4
            f += 1
        return ms + f * 64
