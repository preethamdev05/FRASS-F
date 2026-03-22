"""Face engine singleton — cross-worker cache invalidation via Redis pub/sub."""

import logging
import threading
from app.services.face_engine import FaceEngine, ENCODING_VERSION_KEY
from app.services.hardware import get_hardware_profile

logger = logging.getLogger(__name__)

_engine: FaceEngine | None = None
_listener_started = False
_local_version: int = 0


def get_face_engine() -> FaceEngine:
    """Get or create the face engine singleton."""
    global _engine
    if _engine is None:
        from flask import current_app
        profile = get_hardware_profile()
        hw_config = profile.optimal_config()
        _engine = FaceEngine(
            config=hw_config,
            face_data_dir=current_app.config['FACE_DATA_DIR'],
            model_name=current_app.config.get('FACE_MODEL', 'buffalo_l'),
        )
        _engine.load_all_encodings()
        _start_invalidation_listener()
    return _engine


def _start_invalidation_listener():
    """Start a background thread that reloads encodings when Redis version changes."""
    global _listener_started
    if _listener_started:
        return

    from app.extensions import get_redis
    r = get_redis()
    if not r:
        return

    try:
        global _local_version
        _local_version = int(r.get(ENCODING_VERSION_KEY) or 0)
    except Exception:
        pass

    def _poll_loop():
        global _local_version, _engine
        import time
        while True:
            try:
                remote_version = int(r.get(ENCODING_VERSION_KEY) or 0)
                if remote_version != _local_version:
                    logger.info('Cache version changed (%d -> %d), reloading encodings',
                                _local_version, remote_version)
                    _local_version = remote_version
                    if _engine:
                        _engine.load_all_encodings()
            except Exception:
                pass
            time.sleep(2)  # Poll every 2 seconds

    t = threading.Thread(target=_poll_loop, daemon=True, name='face-cache-listener')
    t.start()
    _listener_started = True
    logger.info('Cache invalidation listener started (polling every 2s)')


def preload_engine(app):
    """Pre-load face engine at startup (avoids cold start on first request)."""
    with app.app_context():
        try:
            get_face_engine()
            app.logger.info('Face engine pre-loaded successfully')
        except Exception as e:
            app.logger.warning('Face engine pre-load failed (will lazy-load): %s', e)
