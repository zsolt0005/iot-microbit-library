"""The simulator answers like the real module: replay of data/esp_at_recording.txt."""

import ast
import os
import re

from esp_at import EspAt, args, topic_matches

RECORDING = os.path.join(os.path.dirname(__file__), "data", "esp_at_recording.txt")
REQUEST = (
    b"GET /channels/9/feeds.json?results=0 HTTP/1.1\r\n"
    b"Host: api.thingspeak.com\r\nConnection: close\r\n\r\n"
)


def load():
    """Return [(command, [(ms, bytes)], end_ms)] from the recording."""
    blocks = []
    for line in open(RECORDING):
        line = line.rstrip("\n")
        if line.startswith(">> "):
            blocks.append((line[3:], [], []))
        elif line.startswith("  end "):
            blocks[-1][2].append(int(line.split()[1]))
        elif line.startswith("  "):
            ms, data = line.split(" ", 3)[2:]
            blocks[-1][1].append((int(ms), ast.literal_eval(data)))
    return [(cmd, chunks, end[0]) for cmd, chunks, end in blocks]


def test_simulator_replays_the_recording():
    blocks = load()
    joined = b"".join(b"".join(d for _, d in chunks) for _, chunks, _ in blocks)
    topic = re.search(rb'MQTTSUBRECV:0,"([^"]+)"', joined).group(1).decode()
    http = next(b"".join(d for _, d in c) for cmd, c, _ in blocks if cmd.startswith("<request"))
    i = http.find(b"+IPD,")
    colon = http.find(b":", i)
    body = http[colon + 1 : colon + 1 + int(http[i + 5 : colon])]
    sim = EspAt(networks={"<ssid>": "<password>"}, servers={"api.thingspeak.com": lambda r: body})

    for cmd, chunks, end in blocks:
        start = sim.now
        if cmd.startswith("<request"):
            sim.write(REQUEST)
        elif cmd == "AT+MQTTPUB then AT+CIPSTATUS at once":
            sim.write('AT+MQTTPUB=0,"%s","second",1,0\r\nAT+CIPSTATUS\r\n' % topic)
        elif not cmd.startswith(("idle", "wake-up")):
            sim.read()
            sim.write(cmd.replace("<topic>", topic) + "\r\n")
        times = [t - start for t, _ in sim._out if t <= start + end]
        sim.now = start + end
        got = sim.read() or b""
        expected = b"".join(d for _, d in chunks)
        if cmd == "AT+GMR":
            continue  # the real module joined Wi-Fi by itself during this answer
        if "<wrong>" in cmd:
            assert got == expected[expected.find(b"+CWJAP") :], cmd  # it was online before
        else:
            assert got == expected, cmd
        if chunks:
            last = chunks[-1][0]
            assert abs(times[-1] - last) <= max(30, last * 0.15), (cmd, times[-1], last)


def test_args_and_topics():
    assert args('0,"a,b",1') == ["0", "a,b", "1"]
    assert args(r'"x\"y","",2') == ['x"y', "", "2"]
    assert topic_matches("domov/#", "domov/kuchyna/teplota")
    assert topic_matches("domov/+/teplota", "domov/kuchyna/teplota")
    assert not topic_matches("domov/+", "domov/kuchyna/teplota")


def test_unsolicited_line_inside_an_answer():
    sim = EspAt()
    sim.inject('+MQTTSUBRECV:0,"t",2,ON', during="AT+CIPSTATUS")
    sim.write("AT+CIPSTATUS\r\n")
    sim.now = 100
    assert sim.read() == b'AT+CIPSTATUS\r\n+MQTTSUBRECV:0,"t",2,ON\r\nSTATUS:5\r\n\r\nOK\r\n'
