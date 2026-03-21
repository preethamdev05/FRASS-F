"""Face engine singleton — pre-loaded at app startup."""

from app.services.face_engine import FaceEngine
from app.services.hardware import get_hardware_profile

_engine: FaceEngine | None = None


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
    return _engine


def preload_engine(app):
    """Pre-load face engine at startup (avoids cold start on first request)."""
    with app.app_context():
        try:
            get_face_engine()
            app.logger.info('Face engine pre-loaded successfully')
        except Exception as e:
            app.logger.warning('Face engine pre-load failed (will lazy-load): %s', e)
