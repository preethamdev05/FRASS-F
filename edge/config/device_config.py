"""Device configuration with runtime updates."""

import json
import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    'device_id': 'edge-001',
    'backend_url': 'http://localhost:8000',
    'mqtt_broker': 'localhost',
    'mqtt_port': 1883,
    'mqtt_topic_prefix': 'fras',

    'camera_device': 0,
    'camera_fps': 15,
    'camera_width': 640,
    'camera_height': 480,
    'frame_skip': 2,

    'model_type': 'auto',  # auto, lightweight, full
    'face_det_size': 480,
    'recognition_threshold': 0.65,
    'liveness_threshold': 0.65,
    'anti_spoof_model': '',  # path to MiniFASNet ONNX

    'offline_queue_max': 1000,
    'sync_interval': 30,
    'config_poll_interval': 60,

    'tls_enabled': True,
    'api_key': '',
}


class DeviceConfig:
    """Thread-safe device configuration with file persistence and runtime updates."""

    def __init__(self, path: str = 'edge_config.json'):
        self._path = path
        self._config: dict = {}
        self._load()

    def _load(self):
        """Load config from file, falling back to defaults."""
        self._config = dict(DEFAULT_CONFIG)
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    file_config = json.load(f)
                self._config.update(file_config)
                logger.info('Config loaded from %s', self._path)
            except Exception as e:
                logger.warning('Failed to load config: %s', e)

        # Environment overrides
        for key in self._config:
            env_key = f'FRAS_{key.upper()}'
            env_val = os.environ.get(env_key)
            if env_val is not None:
                self._config[key] = self._cast(env_val, type(self._config[key]))

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        self._config[key] = value

    def merge(self, updates: dict):
        """Merge remote config updates (only known keys)."""
        for key, value in updates.items():
            if key in DEFAULT_CONFIG:
                self._config[key] = value

    def save(self):
        """Persist config to file."""
        try:
            with open(self._path, 'w') as f:
                json.dump(self._config, f, indent=2)
        except Exception as e:
            logger.warning('Failed to save config: %s', e)

    def to_dict(self) -> dict:
        return dict(self._config)

    @staticmethod
    def _cast(value: str, target_type: type):
        if target_type is bool:
            return value.lower() in ('true', '1', 'yes')
        if target_type is int:
            return int(value)
        if target_type is float:
            return float(value)
        return value
