"""BME280 temperature, pressure and humidity sensor (ELECFREAKS Smart Science IoT Kit)."""
from microbit import i2c, sleep
from ustruct import unpack_from

NORMAL = 3  # measures continuously, read() returns the latest result at once
FORCED = 1  # measures only on read() and sleeps in between (lower power, slower read())


class BME280:
    def __init__(self, mode=NORMAL, addr=0x76):
        """Check the chip, read its calibration data and start it in the given mode."""
        self._addr = addr
        self._mode = mode
        if self._reg(0xD0, 1)[0] != 0x60:
            raise OSError("BME280 not found")
        c = self._reg(0x88, 26)
        (self._t1, self._t2, self._t3, self._p1, self._p2, self._p3, self._p4, self._p5,
         self._p6, self._p7, self._p8, self._p9) = unpack_from("<HhhHhhhhhhhh", c)
        self._h1 = c[25]
        c = self._reg(0xE1, 7)
        self._h2, self._h3 = unpack_from("<hB", c)
        e4, _, e6, self._h6 = unpack_from("bBbb", c, 3)  # signed E4, E6, E7
        self._h4 = (e4 << 4) | (c[4] & 0x0F)
        self._h5 = (e6 << 4) | (c[4] >> 4)
        i2c.write(addr, b"\xf2\x04")  # humidity oversampling x8
        i2c.write(addr, b"\xf5\x0c")  # standby 0.5 ms, filter x4
        i2c.write(addr, bytes((0xF4, 0x2C | mode)))  # temperature x1, pressure x4, mode

    def _reg(self, reg, n):
        i2c.write(self._addr, bytes((reg,)))
        return i2c.read(self._addr, n)

    def read(self):
        """Return (temperature °C, pressure Pa, humidity %) from one measurement, or None."""
        if self._mode == FORCED:
            i2c.write(self._addr, bytes((0xF4, 0x2C | FORCED)))
            sleep(5)
            while self._reg(0xF3, 1)[0] & 0x08:  # still measuring
                sleep(2)
        for _ in range(20):
            d = self._reg(0xF7, 8)  # burst read: pressure, temperature, humidity
            if d[3] != 0x80 or d[4] or d[5]:
                break
            sleep(5)  # 0x800000 = no measurement yet (right after power-up)
        else:
            return None
        adc_p = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
        adc_t = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
        adc_h = (d[6] << 8) | d[7]
        # Bosch integer compensation from the BME280 datasheet, as in the original library
        v1 = (((adc_t >> 3) - (self._t1 << 1)) * self._t2) >> 11
        v2 = (((((adc_t >> 4) - self._t1) * ((adc_t >> 4) - self._t1)) >> 12) * self._t3) >> 14
        t = v1 + v2
        temp = ((t * 5 + 128) >> 8) / 100
        v1 = (t >> 1) - 64000
        v2 = (((v1 >> 2) * (v1 >> 2)) >> 11) * self._p6
        v2 = v2 + ((v1 * self._p5) << 1)
        v2 = (v2 >> 2) + (self._p4 << 16)
        v1 = (((self._p3 * (((v1 >> 2) * (v1 >> 2)) >> 13)) >> 3) + ((self._p2 * v1) >> 1)) >> 18
        v1 = ((32768 + v1) * self._p1) >> 15
        if v1 == 0:
            return None
        p = ((((1048576 - adc_p) - (v2 >> 12)) * 3125) << 1) // v1
        v2 = (self._p9 * (((p >> 3) * (p >> 3)) >> 13)) >> 12
        p = p + ((v2 + (((p >> 2) * self._p8) >> 13) + self._p7) >> 4)
        v1 = t - 76800
        v2 = (((adc_h << 14) - (self._h4 << 20) - (self._h5 * v1)) + 16384) >> 15
        v1 = v2 * (((((((v1 * self._h6) >> 10) * (((v1 * self._h3) >> 11) + 32768)) >> 10)
                     + 2097152) * self._h2 + 8192) >> 14)
        v1 = v1 - (((((v1 >> 15) * (v1 >> 15)) >> 7) * self._h1) >> 4)
        v1 = 0 if v1 < 0 else 419430400 if v1 > 419430400 else v1
        return temp, p, (v1 >> 12) / 1024

    def temperature(self):
        """Return temperature in °C (one measurement)."""
        r = self.read()
        return r[0] if r else None

    def pressure(self):
        """Return pressure in Pa (one measurement)."""
        r = self.read()
        return r[1] if r else None

    def humidity(self):
        """Return relative humidity in % (one measurement)."""
        r = self.read()
        return r[2] if r else None
