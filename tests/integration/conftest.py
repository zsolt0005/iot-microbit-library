"""Broker from tests/integration/compose.yaml; settings come from environment variables."""

import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import paho.mqtt.client  # noqa: F401  before the fakes: our http.py must not hide CPython's http
import pytest

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent / "unit"

# micro:bit fakes and the ESP-AT simulator from the unit tests
sys.path.insert(0, str(UNIT))
_spec = importlib.util.spec_from_file_location("unit_fakes", UNIT / "conftest.py")
assert _spec and _spec.loader
_spec.loader.exec_module(importlib.util.module_from_spec(_spec))


@dataclass(frozen=True)
class Broker:
    host: str
    port: int
    user: str
    password: str


@pytest.fixture(scope="session")
def broker():
    return Broker(
        os.environ.get("MQTT_HOST", "127.0.0.1"),
        int(os.environ.get("MQTT_PORT", "1883")),
        os.environ["MQTT_USER"],
        os.environ["MQTT_PASSWORD"],
    )


@pytest.fixture(scope="session")
def compose_text():
    return (HERE / "compose.yaml").read_text()


@pytest.fixture
def node(broker, monkeypatch):
    """micro:bit library (wifi, mqtt) on the simulator, MQTT commands go to the real broker."""
    from bridge import BridgedEspAt

    import mqtt
    import wifi

    module = BridgedEspAt(broker, networks={"Domov": "heslo"})
    for name, value in (("uart", module), ("sleep", module.sleep), ("ticks_ms", module.ticks_ms),
                        ("_ready", False), ("on_data", wifi._keep_all)):  # fmt: skip
        monkeypatch.setattr(wifi, name, value)
    state = {"uart": module, "sleep": module.sleep, "_messages": [], "_partial": b"",
             "_server": None, "_topics": [], "dropped": 0}  # fmt: skip
    for name, value in state.items():
        monkeypatch.setattr(mqtt, name, value)
    yield module
    module._close()
