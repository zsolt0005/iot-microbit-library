"""mqtt.py end to end: library -> simulated Wi-Fi module -> real Mosquitto (step 2.5)."""

import json
import time
import uuid

import pytest
from test_mosquitto import Client

import mqtt
import wifi


def wait_message(node, timeout=5):
    """Poll like a node program; the simulator clock moves with real time."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        m = mqtt.message()
        if m:
            return m
        time.sleep(0.01)
        node.sleep(10)
    return None


@pytest.fixture
def topic():
    return "test/" + uuid.uuid4().hex


@pytest.fixture
def peer(broker):
    """Another MQTT client, e.g. Home Assistant."""
    client = Client(broker, user=broker.user, password=broker.password)
    yield client
    client.close()


def online(broker):
    assert wifi.connect("Domov", "heslo")
    return mqtt.connect("broker", "node-" + uuid.uuid4().hex, broker.user, broker.password)


def test_login_checked_by_the_broker(node, broker):
    assert wifi.connect("Domov", "heslo")
    assert mqtt.connect("broker", "node", broker.user, broker.password + "-wrong") is False
    assert mqtt.connect("broker", "node", broker.user, broker.password) is True


def test_node_publishes_json(node, broker, peer, topic):
    assert online(broker)
    peer.subscribe(topic)
    data = mqtt.json({"t": 1795276800, "teplota": 21.5, "miesto": 'kuchyňa "A", okno'})
    assert mqtt.publish(topic, data) is True
    message = peer.receive()
    assert message.qos == 1
    assert json.loads(message.payload) == {"t": 1795276800, "teplota": 21.5,
                                           "miesto": 'kuchyňa "A", okno'}  # fmt: skip


def test_node_receives_messages(node, broker, peer, topic):
    assert online(broker)
    assert mqtt.subscribe(topic + "/#")
    peer.publish(topic + "/config/interval", "60")
    peer.publish(topic + "/config/text", 'a,"b"\r\nc')
    assert wait_message(node) == (topic + "/config/interval", "60")
    assert wait_message(node) == (topic + "/config/text", 'a,"b"\r\nc')


def test_retained_command_after_outage(node, broker, peer, topic):
    assert online(broker)
    assert mqtt.subscribe(topic)
    wifi.disconnect()
    peer.publish(topic, "OFF", retain=True)
    peer.publish(topic, "ON", retain=True)  # changed again while the node was offline
    assert mqtt.check("Domov", "heslo") is True
    assert wait_message(node) == (topic, "ON")
    peer.publish(topic, b"", retain=True)


def test_node_state_is_retained_for_new_clients(node, broker, topic):
    assert online(broker)
    assert mqtt.publish(topic, "ON", retain=True) is True
    later = Client(broker, user=broker.user, password=broker.password)
    try:
        later.subscribe(topic)
        message = later.receive()
        assert message.retain and message.payload == b"ON"
    finally:
        mqtt.publish(topic, "", retain=True)
        later.close()
