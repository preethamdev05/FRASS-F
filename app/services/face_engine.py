"""Face recognition engine with hardware-adaptive configuration."""

import logging
import pickle
import time
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class FaceEngine:
    """Hardware-adaptive face detection, encoding, and recognition."""

    def __init__(self, config: dict, face_data_dir: str, model_name: str = 'buffalo_l'):
        self.config = config
        self.face_data_dir = face_data_dir
        self.model_name = model_name
        self._app = None
        self._known_encodings = {}  # {student_db_id: [encoding_arrays]}
        self._known_ids = []

    @property
    def app(self):
        """Lazy-load InsightFace."""
        if self._app is None:
            self._load_model()
        return self._app

    def _load_model(self):
        """Load InsightFace with optimal providers."""
        import insightface
        from insightface.app import FaceAnalysis

        providers = self.config.get('providers', ['CPUExecutionProvider'])
        det_size = self.config.get('face_det_size', 640)

        logger.info(f'Loading InsightFace model: {self.model_name}')
        logger.info(f'Providers: {providers}')
        logger.info(f'Detection size: {det_size}')

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
            faces = self.app.get(frame)
            return faces
        except Exception as e:
            logger.error(f'Face detection error: {e}')
            return []

    def encode_face(self, frame: np.ndarray, face) -> Optional[np.ndarray]:
        """Get embedding for a detected face."""
        try:
            return face.normed_embedding
        except Exception as e:
            logger.error(f'Face encoding error: {e}')
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
            logger.error(f'Image encoding error: {e}')
            return None, f'Error processing image: {str(e)}'

    def save_encoding(self, student_db_id: int, encoding: np.ndarray, photo_path: str = None):
        """Save a face encoding to in-memory cache."""
        if student_db_id not in self._known_encodings:
            self._known_encodings[student_db_id] = []
        self._known_encodings[student_db_id].append(encoding)

    def load_all_encodings(self):
        """Load all face encodings from database into memory."""
        from app.models.face import FaceEncoding

        self._known_encodings = {}

        try:
            records = FaceEncoding.query.all()
            for rec in records:
                try:
                    enc = pickle.loads(rec.encoding_blob)
                    if rec.student_id not in self._known_encodings:
                        self._known_encodings[rec.student_id] = []
                    self._known_encodings[rec.student_id].append(enc)
                except Exception as e:
                    logger.warning(f'Failed to decode FaceEncoding id={rec.id}: {e}')
        except Exception as e:
            logger.error(f'Failed to load encodings from database: {e}')

        total = sum(len(v) for v in self._known_encodings.values())
        logger.info(f'Loaded {total} face encodings for {len(self._known_encodings)} students from database')

    def recognize_face(self, encoding: np.ndarray, tolerance: float = 0.5) -> Tuple[Optional[int], float]:
        """Match a face encoding against known encodings."""
        if not self._known_encodings:
            return None, 0.0

        best_id = None
        best_score = 0.0

        for student_db_id, encodings in self._known_encodings.items():
            for known_enc in encodings:
                similarity = np.dot(encoding, known_enc)
                if similarity > best_score:
                    best_score = similarity
                    best_id = student_db_id

        confidence = round(float(best_score) * 100, 1)

        if best_score >= tolerance:
            return best_id, confidence
        return None, confidence

    def recognize_faces_batch(self, encodings: List[np.ndarray], tolerance: float = 0.5) -> list:
        """Recognize multiple faces at once."""
        results = []
        for enc in encodings:
            sid, conf = self.recognize_face(enc, tolerance)
            results.append((sid, conf))
        return results

    def delete_student_encodings(self, student_db_id: int):
        """Remove all encodings for a student from cache and database."""
        from app.models.face import FaceEncoding
        from app.extensions import db

        self._known_encodings.pop(student_db_id, None)
        FaceEncoding.query.filter_by(student_id=student_db_id).delete()
        db.session.commit()

    @property
    def stats(self):
        total_encodings = sum(len(v) for v in self._known_encodings.values())
        return {
            'students_with_faces': len(self._known_encodings),
            'total_encodings': total_encodings,
            'config': self.config,
        }
