"""Edge inference pipeline — detect, align, embed, liveness.

Runs entirely on-device. Sends only embeddings + metadata to backend.
Optimized for low-power hardware (RPi, Jetson Nano).
"""

import logging
import time
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)


class InferencePipeline:
    """End-to-end face processing pipeline for edge devices."""

    def __init__(self, config):
        self.config = config
        self._detector = None
        self._antispoof = None
        self._init_models()

    def _init_models(self):
        """Initialize face detection and anti-spoofing models."""
        model_type = self.config.get('model_type', 'auto')
        det_size = self.config.get('face_det_size', 480)

        # Auto-select model based on available hardware
        if model_type == 'auto':
            try:
                import onnxruntime as ort
                providers = ort.get_available_providers()
                if 'CUDAExecutionProvider' in providers:
                    model_type = 'full'
                elif 'OpenVINOExecutionProvider' in providers:
                    model_type = 'full'
                else:
                    model_type = 'lightweight'
            except Exception:
                model_type = 'lightweight'

        try:
            from insightface.app import FaceAnalysis
            model_name = 'buffalo_s' if model_type == 'lightweight' else 'buffalo_l'
            self._detector = FaceAnalysis(
                name=model_name,
                allowed_modules=['detection', 'recognition'],
            )
            self._detector.prepare(ctx_id=0, det_size=(det_size, det_size))
            logger.info('Face model loaded: %s (det_size=%d)', model_name, det_size)
        except ImportError:
            logger.error('insightface not installed')
            raise

        # Anti-spoofing model (optional)
        spoof_path = self.config.get('anti_spoof_model', '')
        if spoof_path:
            try:
                import onnxruntime as ort
                self._antispoof = ort.InferenceSession(spoof_path)
                self._antispoof_input = self._antispoof.get_inputs()[0].name
                self._antispoof_output = self._antispoof.get_outputs()[0].name
                logger.info('Anti-spoof model loaded: %s', spoof_path)
            except Exception as e:
                logger.warning('Anti-spoof model not loaded: %s', e)

    def process(self, frame: np.ndarray) -> Optional[dict]:
        """Process a single frame through the full pipeline.

        Returns:
            dict with embedding, liveness scores, and metadata
            None if no face detected or quality too low
        """
        start = time.time()

        # 1. Detect faces
        try:
            faces = self._detector.get(frame)
        except Exception as e:
            logger.error('Detection error: %s', e)
            return None

        if not faces:
            return None

        # Process only the largest face (closest to camera)
        face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))

        # 2. Extract aligned face crop
        bbox = face.bbox.astype(int)
        face_roi = frame[bbox[1]:bbox[3], bbox[0]:bbox[2]]
        landmarks = face.kps if hasattr(face, 'kps') else None

        # 3. Quality check
        quality = self._check_quality(face_roi)
        if not quality['pass']:
            return None

        # 4. Get embedding (512-D ArcFace)
        embedding = face.normed_embedding
        if embedding is None:
            return None

        # 5. Liveness detection
        liveness_score = self._compute_liveness(face_roi, landmarks)

        # 6. Build result (NO raw image data — only embedding + metadata)
        result = {
            'embedding': embedding.tolist(),  # 512 floats
            'bbox': bbox.tolist(),
            'quality': quality,
            'liveness_score': round(liveness_score, 3),
            'is_live': liveness_score >= self.config.get('liveness_threshold', 0.65),
            'latency_ms': round((time.time() - start) * 1000, 1),
        }

        if landmarks is not None:
            result['landmarks'] = landmarks.tolist()

        return result

    def _check_quality(self, face_roi: np.ndarray) -> dict:
        """Quick quality check: blur + brightness."""
        import cv2
        if face_roi is None or face_roi.size == 0:
            return {'pass': False, 'reason': 'empty'}

        h, w = face_roi.shape[:2]
        if h < 60 or w < 60:
            return {'pass': False, 'reason': 'too_small'}

        gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
        blur = cv2.Laplacian(gray, cv2.CV_64F).var()
        brightness = float(np.mean(gray))

        pass_check = blur > 30 and 30 < brightness < 230
        return {
            'pass': pass_check,
            'blur': round(blur, 1),
            'brightness': round(brightness, 1),
            'resolution': f'{w}x{h}',
        }

    def _compute_liveness(self, face_roi: np.ndarray, landmarks) -> float:
        """Fuse heuristic + ML anti-spoofing scores."""
        heuristic = self._heuristic_liveness(face_roi)
        ml_score = self._ml_antispoof(face_roi)

        if ml_score >= 0:
            return 0.6 * ml_score + 0.4 * heuristic
        return heuristic

    def _heuristic_liveness(self, face_roi: np.ndarray) -> float:
        """Fast heuristic liveness (texture + colorspace)."""
        import cv2
        try:
            gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)

            # Texture variance
            h, w = gray.shape
            block_size = 8
            variances = []
            for y in range(0, h - block_size, block_size):
                for x in range(0, w - block_size, block_size):
                    block = gray[y:y + block_size, x:x + block_size].astype(np.float32)
                    variances.append(np.var(block))
            texture_score = min(1.0, np.mean(variances) / 200.0) if variances else 0.5

            # YCrCb skin detection
            ycrcb = cv2.cvtColor(face_roi, cv2.COLOR_BGR2YCrCb)
            lower = np.array([0, 133, 77], dtype=np.uint8)
            upper = np.array([255, 173, 127], dtype=np.uint8)
            mask = cv2.inRange(ycrcb, lower, upper)
            skin_ratio = np.count_nonzero(mask) / (mask.size + 1e-6)
            skin_score = 0.8 if 0.15 <= skin_ratio <= 0.75 else 0.4

            return 0.5 * texture_score + 0.5 * skin_score
        except Exception:
            return 0.5

    def _ml_antispoof(self, face_roi: np.ndarray) -> float:
        """ML anti-spoofing inference. Returns -1 if model unavailable."""
        if self._antispoof is None:
            return -1.0

        try:
            import cv2
            resized = cv2.resize(face_roi, (224, 224))
            blob = resized.astype(np.float32) / 255.0
            blob = np.transpose(blob, (2, 0, 1))
            blob = np.expand_dims(blob, axis=0)

            output = self._antispoof.run([self._antispoof_output], {self._antispoof_input: blob})
            raw = output[0]

            if raw.shape[-1] >= 2:
                exp = np.exp(raw[0] - np.max(raw[0]))
                probs = exp / exp.sum()
                return float(probs[1])
            return float(raw[0][0])
        except Exception:
            return -1.0
