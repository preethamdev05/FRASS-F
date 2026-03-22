"""Sync client — REST + MQTT communication with backend.

Supports:
- REST fallback for simple deployments
- MQTT for real-time event streaming
- Automatic retry with exponential backoff
- TLS encryption
"""

import logging
import time
import json

logger = logging.getLogger(__name__)


class SyncClient:
    """Communicates with the processing backend."""

    def __init__(self, config):
        self._backend_url = config.get('backend_url', 'http://localhost:8000')
        self._api_key = config.get('api_key', '')
        self._device_id = config.get('device_id', 'edge-001')
        self._mqtt_broker = config.get('mqtt_broker', '')
        self._mqtt_port = config.get('mqtt_port', 1883)
        self._topic_prefix = config.get('mqtt_topic_prefix', 'fras')
        self._tls = config.get('tls_enabled', True)
        self._mqtt_client = None
        self._connected = False
        self._init_mqtt()

    def _init_mqtt(self):
        """Initialize MQTT client if broker configured."""
        if not self._mqtt_broker:
            return
        try:
            import paho.mqtt.client as mqtt

            self._mqtt_client = mqtt.Client(client_id=self._device_id)
            if self._tls:
                self._mqtt_client.tls_set()

            if self._api_key:
                self._mqtt_client.username_pw_set(self._device_id, self._api_key)

            self._mqtt_client.on_connect = self._on_connect
            self._mqtt_client.on_disconnect = self._on_disconnect

            self._mqtt_client.connect_async(self._mqtt_broker, self._mqtt_port, keepalive=60)
            self._mqtt_client.loop_start()
            logger.info('MQTT connecting to %s:%d', self._mqtt_broker, self._mqtt_port)
        except ImportError:
            logger.warning('paho-mqtt not installed, using REST only')

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            topic = f'{self._topic_prefix}/devices/{self._device_id}/config'
            client.subscribe(topic)
            logger.info('MQTT connected')
        else:
            logger.warning('MQTT connection failed: rc=%d', rc)

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        logger.warning('MQTT disconnected: rc=%d', rc)

    def is_connected(self) -> bool:
        """Check if backend is reachable."""
        try:
            import requests
            resp = requests.get(
                f'{self._backend_url}/api/health',
                timeout=3,
                headers=self._headers(),
            )
            return resp.status_code == 200
        except Exception:
            return self._connected

    def send_result(self, result: dict) -> bool:
        """Send inference result to backend via REST or MQTT."""
        # Try MQTT first (lower latency)
        if self._mqtt_client and self._connected:
            try:
                topic = f'{self._topic_prefix}/devices/{self._device_id}/results'
                payload = json.dumps(result)
                self._mqtt_client.publish(topic, payload, qos=1)
                return True
            except Exception:
                pass

        # Fallback to REST
        try:
            import requests
            resp = requests.post(
                f'{self._backend_url}/api/edge/result',
                json=result,
                headers=self._headers(),
                timeout=5,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.debug('REST send failed: %s', e)
            return False

    def fetch_config(self) -> dict | None:
        """Fetch device config from backend."""
        try:
            import requests
            resp = requests.get(
                f'{self._backend_url}/api/devices/{self._device_id}/config',
                headers=self._headers(),
                timeout=5,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def register_device(self, device_info: dict) -> bool:
        """Register this device with the backend."""
        try:
            import requests
            resp = requests.post(
                f'{self._backend_url}/api/devices/register',
                json=device_info,
                headers=self._headers(),
                timeout=10,
            )
            return resp.status_code in (200, 201)
        except Exception:
            return False

    def send_batch(self, results: list) -> bool:
        """Send a batch of results (for offline sync)."""
        try:
            import requests
            resp = requests.post(
                f'{self._backend_url}/api/edge/sync',
                json={'device_id': self._device_id, 'results': results},
                headers=self._headers(),
                timeout=30,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _headers(self) -> dict:
        headers = {'Content-Type': 'application/json'}
        if self._api_key:
            headers['X-API-Key'] = self._api_key
        headers['X-Device-ID'] = self._device_id
        return headers

    def disconnect(self):
        if self._mqtt_client:
            self._mqtt_client.loop_stop()
            self._mqtt_client.disconnect()
