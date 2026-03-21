"""Face engine singleton accessor."""

from flask import current_app
from app.services.face_engine import FaceEngine
from app.services.hardware import get_hardware_profile

_engine = None


def get_face_engine() -> FaceEngine:
    """Get or create the face engine singleton."""
    global _engine
    if _engine is None:
        profile = get_hardware_profile()
        config = profile.optimal_config()
        _engine = FaceEngine(
            config=config,
            face_data_dir=current_app.config['FACE_DATA_DIR'],
            model_name=current_app.config.get('FACE_MODEL', 'buffalo_l'),
        )
        _engine.load_all_encodings()
    return _engine
