"""ML-based anti-spoofing using MiniFASNet (ONNX inference).

Provides a learned binary classifier (live vs spoof) that complements
the heuristic liveness stack. Trained on datasets like CelebA-Spoof
and SiW-Mv2 to detect deepfakes, 3D masks, and screen replay attacks.

Fusion strategy:
    final_score = alpha * ml_score + (1 - alpha) * heuristic_score
"""

import logging
import os
import numpy as np

logger = logging.getLogger(__name__)

# Anti-spoofing model input spec (MiniFASNet)
_SPOOF_INPUT_SIZE = (224, 224)


class AntiSpoofDetector:
    """ML-based anti-spoofing classifier using ONNX Runtime."""

    def __init__(self, model_path: str = ''):
        self._session = None
        self._input_name = None
        self._output_name = None
        self._model_path = model_path or self._find_default_model()

    def _find_default_model(self) -> str:
        """Search for anti-spoof model in standard locations."""
        candidates = [
            'models/2.7_80x80_MiniFASNetV2.onnx',
            'models/4_0_0_80x80_MiniFASNetV1SE.onnx',
            'models/antispoof.onnx',
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return ''

    @property
    def available(self) -> bool:
        """Check if model is loaded."""
        return self._session is not None

    def _load_model(self):
        """Lazy-load ONNX model."""
        if not self._model_path:
            logger.info('No anti-spoof model configured, ML liveness disabled')
            return

        try:
            import onnxruntime as ort

            providers = ['CPUExecutionProvider']
            try:
                available = ort.get_available_providers()
                if 'CUDAExecutionProvider' in available:
                    providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
            except Exception:
                pass

            self._session = ort.InferenceSession(self._model_path, providers=providers)
            self._input_name = self._session.get_inputs()[0].name
            self._output_name = self._session.get_outputs()[0].name
            logger.info('Anti-spoof model loaded: %s (providers: %s)', self._model_path, providers)
        except Exception as e:
            logger.warning('Failed to load anti-spoof model: %s', e)
            self._session = None

    def predict(self, face_roi: np.ndarray) -> float:
        """Predict liveness probability for a face crop.

        Args:
            face_roi: BGR face crop (any size, will be resized to 224x224)

        Returns:
            Probability of being a real face (0.0 = spoof, 1.0 = live)
        """
        if self._session is None:
            self._load_model()
        if self._session is None:
            return -1.0  # Signal: model unavailable

        try:
            import cv2

            # Preprocess: resize, normalize to [0, 1], CHW format
            resized = cv2.resize(face_roi, _SPOOF_INPUT_SIZE)
            blob = resized.astype(np.float32) / 255.0
            blob = np.transpose(blob, (2, 0, 1))  # HWC -> CHW
            blob = np.expand_dims(blob, axis=0)    # Add batch dim

            # Run inference
            outputs = self._session.run([self._output_name], {self._input_name: blob})
            raw = outputs[0]

            # Model output can be:
            # - [1] sigmoid scalar -> use directly
            # - [2] softmax -> index 1 is live probability
            if raw.shape[-1] == 1:
                return float(raw[0][0])
            elif raw.shape[-1] >= 2:
                # Softmax
                exp = np.exp(raw[0] - np.max(raw[0]))
                probs = exp / exp.sum()
                return float(probs[1])  # Index 1 = live
            else:
                return float(raw[0])

        except Exception as e:
            logger.warning('Anti-spoof inference failed: %s', e)
            return -1.0


def fuse_liveness_scores(ml_score: float, heuristic_score: float, alpha: float = 0.6) -> float:
    """Fuse ML and heuristic liveness scores.

    Args:
        ml_score: ML model probability (0-1, or -1 if unavailable)
        heuristic_score: Heuristic stack score (0-1)
        alpha: Weight for ML score (default 0.6 = ML-dominant)

    Returns:
        Fused score (0-1)
    """
    if ml_score < 0:
        # ML unavailable — rely entirely on heuristics
        return heuristic_score
    return alpha * ml_score + (1 - alpha) * heuristic_score
