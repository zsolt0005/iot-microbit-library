"""MQTT behaviour the nodes rely on, tested on the real Mosquitto container."""

import json
import queue
import re
import uuid

import paho.mqtt.client as mqtt
import pytest

TIMEOUT = 5


class Client:
    def __init__(self, broker, client_id=None, clean=True, user=None, password=None):
        self.connected = queue.Queue()
        self.subscribed = queue.Queue()
        self.messages = queue.Queue()
        self.mqtt = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id or "test-" + uuid.uuid4().hex,
            clean_session=clean,
            protocol=mqtt.MQTTv311,
        )
        if user is not None:
            self.mqtt.username_pw_set(user, password)
        self.mqtt.on_connect = lambda c, u, f, code, p: self.connected.put(code)
        self.mqtt.on_subscribe = lambda c, u, mid, codes, p: self.subscribed.put(codes)
        self.mqtt.on_message = lambda c, u, message: self.messages.put(message)
        self.mqtt.connect(broker.host, broker.port, keepalive=10)
        self.mqtt.loop_start()
        self.code = self.connected.get(timeout=TIMEOUT)

    def subscribe(self, topic, qos=1):
        self.mqtt.subscribe(topic, qos)
        codes = self.subscribed.get(timeout=TIMEOUT)
        assert not codes[0].is_failure

    def publish(self, topic, payload, qos=1, retain=False):
        self.mqtt.publish(topic, payload, qos, retain).wait_for_publish(TIMEOUT)

    def receive(self):
        return self.messages.get(timeout=TIMEOUT)

    def close(self):
        self.mqtt.disconnect()
        self.mqtt.loop_stop()


@pytest.fixture
def connect(broker):
    clients = []

    def factory(client_id=None, clean=True):
        client = Client(broker, client_id, clean, broker.user, broker.password)
        assert not client.code.is_failure
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.close()


@pytest.fixture
def topic():
    return "test/" + uuid.uuid4().hex


def test_broker_version_matches_compose(connect, compose_text):
    expected = re.search(r"eclipse-mosquitto:(\d+\.\d+\.\d+)", compose_text).group(1)
    client = connect()
    client.subscribe("$SYS/broker/version", qos=0)
    assert client.receive().payload.decode() == "mosquitto version " + expected


def test_anonymous_client_is_rejected(broker):
    client = Client(broker)
    client.close()
    assert client.code.is_failure


def test_wrong_password_is_rejected(broker):
    client = Client(broker, user=broker.user, password=broker.password + "-wrong")
    client.close()
    assert client.code.is_failure


def test_qos1_json_round_trip(connect, topic):
    subscriber = connect()
    subscriber.subscribe(topic)
    measurement = {"t": 1795276800, "temperature": 21.5, "humidity": 48}
    connect().publish(topic, json.dumps(measurement))
    message = subscriber.receive()
    assert message.qos == 1
    assert json.loads(message.payload) == measurement


def test_retained_message_reaches_new_subscriber(connect, topic):
    publisher = connect()
    publisher.publish(topic, "22", retain=True)
    subscriber = connect()
    subscriber.subscribe(topic)
    message = subscriber.receive()
    assert message.retain and message.payload == b"22"
    publisher.publish(topic, b"", retain=True)  # remove the retained message


def test_sleeping_node_receives_qos1_after_reconnect(broker, connect, topic):
    node_id = "node-" + uuid.uuid4().hex
    node = Client(broker, node_id, False, broker.user, broker.password)
    node.subscribe(topic)
    node.close()  # the node goes to deep sleep

    connect().publish(topic, "config")

    node = Client(broker, node_id, False, broker.user, broker.password)
    try:
        assert node.receive().payload == b"config"
    finally:
        node.close()
    Client(broker, node_id, True, broker.user, broker.password).close()  # remove the session
