"""Broker from tests/integration/compose.yaml; settings come from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


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
