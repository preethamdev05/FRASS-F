"""Face recognition engine with hardware-adaptive configuration and Redis cache."""

import logging
import pickle
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Redis cache keys
ENCODING_CACHE_KEY = 'face:encodings'
ENCODING_VERSION_KEY = 'face:encodings:version'


class FaceEngine:
    """Hardware-adaptive face detection, encoding, and recognition."""

    def __init__(self, config: dict, face_data_dir: str, model_name: str = 'buffalo_l'):
        self.config = config
        self.face_data_dir = face_data_dir
        self.model_name = model_name
        self._app = None
        self._known_encodings: dict[int, list[np.ndarray]] = {}
        self._cache_version = 0

    @property
    def app(self):
        """Lazy-load InsightFace."""
        if self._app is None:
            self._load_model()
        return self._app

    def _load_model(self):
        """Load InsightFace with optimal providers."""
        try:
            from insightface.app import FaceAnalysis
        except ImportError:
            logger.error('insightface not installed. Run: pip install insightface onnxruntime')
            raise RuntimeError(
                'insightface is required for face recognition. '
                'Install with: pip install insightface onnxruntime'
            )

        providers = self.config.get('providers', ['CPUExecutionProvider'])
        det_size = self.config.get('face_det_size', 640)

        logger.info('Loading InsightFace model: %s', self.model_name)
        logger.info('Providers: %s', providers)

        self._app = FaceAnalysis(
            name=self.model_name,
            providers=providers,
            allowed_modules=['detection', 'recognition'],
        )
        self._app.prepare(ctx_id=0, det_size=(det_size, det_size))
        logger.info('InsightFace model loaded successfully')

    def detect_faces(self, frame: np.ndarray) -> list:
        """Detect faces in frame."""
        try:
            return self.app.get(frame)
        except Exception as e:
            logger.error('Face detection error: %s', e)
            return []

    def encode_face(self, frame: np.ndarray, face) -> Optional[np.ndarray]:
        """Get embedding for a detected face."""
        try:
            return face.normed_embedding
        except Exception as e:
            logger.error('Face encoding error: %s', e)
            return None

    def encode_face_from_image(self, image_bytes: bytes) -> Tuple[Optional[np.ndarray], str]:
        """Decode image and extract face encoding."""
        import cv2

        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if frame is None:
                return None, 'Could not decode image'

            faces = self.detect_faces(frame)
            if not faces:
                return None, 'No face detected. Ensure face is clearly visible and well-lit.'
            if len(faces) > 1:
                return None, 'Multiple faces detected. Ensure only one face is in the frame.'

            encoding = self.encode_face(frame, faces[0])
            if encoding is None:
                return None, 'Could not encode face'

            return encoding, 'OK'

        except Exception as e:
            logger.error('Image encoding error: %s', e)
            return None, f'Error processing image: {str(e)}'

    def save_encoding(self, student_db_id: int, encoding: np.ndarray, photo_path: str = None):
        """Save encoding to in-memory cache and Redis."""
        if student_db_id not in self._known_encodings:
            self._known_encodings[student_db_id] = []
        self._known_encodings[student_db_id].append(encoding)
        self._sync_to_redis()

    def load_all_encodings(self):
        """Load encodings from Redis cache, falling back to database."""
        self._known_encodings = {}

        # Try Redis first
        if self._load_from_redis():
            return

        # Fallback to database
        self._load_from_db()
        self._sync_to_redis()

    def _load_from_redis(self) -> bool:
        """Load encodings from Redis. Returns True if successful."""
        try:
            from app.extensions import get_redis
            r = get_redis()
            if not r:
                return False

            cached = r.get(ENCODING_CACHE_KEY)
            if not cached:
                return False

            data = pickle.loads(cached.encode('latin-1'))
            self._known_encodings = data
            total = sum(len(v) for v in self._known_encodings.values())
            logger.info('Loaded %d encodings for %d students from Redis cache',
                        total, len(self._known_encodings))
            return True
        except Exception as e:
            logger.warning('Redis cache load failed: %s', e)
            return False

    def _load_from_db(self):
        """Load encodings from database."""
        from app.models.face import FaceEncoding

        try:
            records = FaceEncoding.query.all()
            for rec in records:
                try:
                    enc = pickle.loads(rec.encoding_blob)
                    if rec.student_id not in self._known_encodings:
                        self._known_encodings[rec.student_id] = []
                    self._known_encodings[rec.student_id].append(enc)
                except Exception as e:
                    logger.warning('Failed to decode FaceEncoding id=%d: %s', rec.id, e)
        except Exception as e:
            logger.error('Failed to load encodings from database: %s', e)

        total = sum(len(v) for v in self._known_encodings.values())
        logger.info('Loaded %d encodings for %d students from database',
                     total, len(self._known_encodings))

    def _sync_to_redis(self):
        """Sync in-memory encodings to Redis cache."""
        try:
            from app.extensions import get_redis
            r = get_redis()
            if not r:
                return
            data = pickle.dumps(self._known_encodings)
            r.set(ENCODING_CACHE_KEY, data.decode('latin-1'))
            r.incr(ENCODING_VERSION_KEY)
        except Exception as e:
            logger.warning('Redis cache sync failed: %s', e)

    def invalidate_cache(self):
        """Force reload of encodings on next recognition."""
        try:
            from app.extensions import get_redis
            r = get_redis()
            if r:
                r.delete(ENCODING_CACHE_KEY)
                r.incr(ENCODING_VERSION_KEY)
        except Exception:
            pass
        self._known_encodings = {}

    def recognize_face(self, encoding: np.ndarray, tolerance: float = 0.5) -> Tuple[Optional[int], float]:
        """Match a face encoding against known encodings."""
        if not self._known_encodings:
            return None, 0.0

        best_id = None
        best_score = 0.0

        for student_db_id, encodings in self._known_encodings.items():
            for known_enc in encodings:
                similarity = float(np.dot(encoding, known_enc))
                if similarity > best_score:
                    best_score = similarity
                    best_id = student_db_id

        confidence = round(best_score * 100, 1)

        if best_score >= tolerance:
            return best_id, confidence
        return None, confidence

    def recognize_faces_batch(self, encodings: list[np.ndarray], tolerance: float = 0.5) -> list:
        """Recognize multiple faces at once."""
        return [self.recognize_face(enc, tolerance) for enc in encodings]

    def delete_student_encodings(self, student_db_id: int):
        """Remove all encodings for a student from cache and database."""
        from app.models.face import FaceEncoding
        from app.extensions import db

        self._known_encodings.pop(student_db_id, None)
        FaceEncoding.query.filter_by(student_id=student_db_id).delete()
        db.session.commit()
        self._sync_to_redis()

    @property
    def stats(self):
        total_encodings = sum(len(v) for v in self._known_encodings.values())
        return {
            'students_with_faces': len(self._known_encodings),
            'total_encodings': total_encodings,
            'config': {k: v for k, v in self.config.items() if k != 'providers'},
        }
