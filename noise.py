"""Noise sensor (ELECFREAKS Smart Science IoT Kit), same algorithm as MakeCode."""

# Groups of 5: (upper amplitude, x0, x1, dB0, dB1); amplitude x0..x1 maps to dB0..dB1.
# Copied from the MakeCode block, including its small gaps between segments.
# fmt: off
_SEGMENTS = (
    4, 0, 4, 30, 50,
    8, 4, 8, 50, 55,
    14, 9, 14, 55, 60,
    32, 15, 32, 60, 70,
    60, 33, 60, 70, 75,
    100, 61, 100, 75, 80,
    150, 101, 150, 80, 85,
    231, 151, 231, 85, 90,
    1023, 231, 1023, 90, 120,
)
# fmt: on


def db(pin, samples=250):
    """Return the noise level in dB (whole number, approximate, not calibrated).

    pin must be an analog pin: P0, P1, P2 (P3, P4, P10 only with display.off()).
    samples: readings per pass (2 passes). MakeCode uses 1000; 250 gives the same
    results in a quarter of the time (about 30 ms).
    """
    read = pin.read_analog
    level = 0
    for _ in range(samples):
        level += read()
    level /= samples
    high = low = sum_high = sum_low = 0
    for _ in range(samples):
        v = read()
        if v >= level:
            high += 1
            sum_high += v
        else:
            low += 1
            sum_low += v
    amp = (sum_high / high if high else level) - (sum_low / low if low else level)
    s = _SEGMENTS
    for i in range(0, 45, 5):
        if amp <= s[i]:
            return round(
                (amp - s[i + 1]) * (s[i + 4] - s[i + 3]) / (s[i + 2] - s[i + 1]) + s[i + 3]
            )
    return 120
