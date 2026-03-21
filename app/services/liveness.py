"""Liveness detection (anti-spoofing) module.

Multi-layer approach:
1. Texture analysis (LBP variance)
2. Moiré pattern detection (FFT)
3. Depth estimation (landmark geometry)
4. Motion/blink detection (EAR)
5. Color space analysis (YCrCb skin distribution)
"""

import logging
import numpy as np
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LivenessResult:
    score: float
    is_live: bool
    breakdown: dict
    reason: str = ''


class LivenessDetector:
    """Multi-layer liveness detection for anti-spoofing."""

    def __init__(self, threshold=0.6, enabled_layers=None):
        self.threshold = threshold
        # Weights for each layer
        self.weights = {
            'texture': 0.25,
            'moire': 0.20,
            'depth': 0.25,
            'motion': 0.20,
            'colorspace': 0.10,
        }
        if enabled_layers:
            # Renormalize weights for enabled layers only
            total = sum(self.weights[k] for k in enabled_layers)
            self.weights = {k: self.weights[k] / total for k in enabled_layers}
        self.enabled = enabled_layers or list(self.weights.keys())

        # Frame history for motion detection
        self._frame_history: List[np.ndarray] = []
        self._max_history = 10

    def analyze(self, face_roi, landmarks=None, frame=None) -> LivenessResult:
        """Run all enabled liveness checks."""
        scores = {}
        reasons = []

        if 'texture' in self.enabled:
            s = self._check_texture(face_roi)
            scores['texture'] = s
            if s < 0.3:
                reasons.append('low texture variance (possible printed photo)')

        if 'moire' in self.enabled:
            s = self._check_moire(face_roi)
            scores['moire'] = s
            if s < 0.3:
                reasons.append('moiré patterns detected (possible screen)')

        if 'depth' in self.enabled and landmarks is not None:
            s = self._check_depth(landmarks)
            scores['depth'] = s
            if s < 0.3:
                reasons.append('flat face geometry (possible 2D photo)')

        if 'motion' in self.enabled and frame is not None:
            s = self._check_motion(face_roi)
            scores['motion'] = s
            if s < 0.2:
                reasons.append('no motion detected (possible static photo)')

        if 'colorspace' in self.enabled:
            s = self._check_colorspace(face_roi)
            scores['colorspace'] = s
            if s < 0.3:
                reasons.append('abnormal skin color distribution')

        # Weighted total
        total = sum(scores.get(k, 0.5) * self.weights.get(k, 0) for k in self.enabled)
        is_live = total >= self.threshold

        reason = '; '.join(reasons) if reasons else 'all checks passed'

        return LivenessResult(
            score=round(total, 3),
            is_live=is_live,
            breakdown={k: round(v, 3) for k, v in scores.items()},
            reason=reason,
        )

    def _check_texture(self, face_roi: np.ndarray) -> float:
        """LBP-based texture analysis. Real faces have micro-texture."""
        try:
            if face_roi is None or face_roi.size == 0:
                return 0.5
            gray = self._to_gray(face_roi)
            if gray is None:
                return 0.5

            # Simplified LBP: compare each pixel to neighbors
            h, w = gray.shape
            if h < 10 or w < 10:
                return 0.5

            # Compute local variance in 8x8 blocks
            block_size = 8
            variances = []
            for y in range(0, h - block_size, block_size):
                for x in range(0, w - block_size, block_size):
                    block = gray[y:y + block_size, x:x + block_size].astype(np.float32)
                    variances.append(np.var(block))

            if not variances:
                return 0.5

            var_mean = np.mean(variances)
            var_std = np.std(variances)

            # Real faces: moderate variance with some spread
            # Photos: either very low variance (smooth print) or very uniform
            # Score based on coefficient of variation
            if var_mean < 10:
                return 0.2  # Too smooth
            elif var_mean > 500:
                return 0.7  # Very textured (could be real or noisy photo)

            cv = var_std / (var_mean + 1e-6)
            # Good texture: cv between 0.3 and 2.0
            if 0.3 <= cv <= 2.5:
                return min(1.0, 0.5 + cv * 0.2)
            return 0.4

        except Exception as e:
            logger.debug(f'Texture check failed: {e}')
            return 0.5

    def _check_moire(self, face_roi: np.ndarray) -> float:
        """FFT-based moiré pattern detection (screens show periodic patterns)."""
        try:
            if face_roi is None or face_roi.size == 0:
                return 0.5
            gray = self._to_gray(face_roi)
            if gray is None:
                return 0.5

            # FFT
            f = np.fft.fft2(gray.astype(np.float32))
            fshift = np.fft.fftshift(f)
            magnitude = np.log(np.abs(fshift) + 1)

            h, w = magnitude.shape
            cy, cx = h // 2, w // 2

            # Look at high-frequency band (exclude DC and very low freq)
            inner_r = min(h, w) // 8
            outer_r = min(h, w) // 2 - 5

            y, x = np.ogrid[:h, :w]
            dist = np.sqrt((y - cy) ** 2 + (x - cx) ** 2)
            band = (dist > inner_r) & (dist < outer_r)

            if not np.any(band):
                return 0.5

            high_freq = magnitude[band]
            # Screens produce strong periodic peaks in frequency domain
            peak_ratio = np.percentile(high_freq, 99) / (np.mean(high_freq) + 1e-6)

            # Lower peak ratio = more natural
            if peak_ratio > 8:
                return 0.2  # Strong periodic pattern = likely screen
            elif peak_ratio > 5:
                return 0.4
            elif peak_ratio > 3:
                return 0.6
            return 0.8

        except Exception as e:
            logger.debug(f'Moiré check failed: {e}')
            return 0.5

    def _check_depth(self, landmarks: np.ndarray) -> float:
        """Estimate 3D depth from facial landmark geometry."""
        try:
            if landmarks is None or len(landmarks) < 5:
                return 0.5

            # InsightFace landmarks: 5 points [left_eye, right_eye, nose, left_mouth, right_mouth]
            pts = landmarks
            if pts.shape == (5, 2):
                left_eye = pts[0]
                right_eye = pts[1]
                nose = pts[2]
                left_mouth = pts[3]
                right_mouth = pts[4]

                # Eye distance (face width reference)
                eye_dist = np.linalg.norm(right_eye - left_eye) + 1e-6

                # Nose-to-eye-line distance (depth indicator)
                eye_center = (left_eye + right_eye) / 2
                nose_depth = np.linalg.norm(nose - eye_center) / eye_dist

                # Mouth center
                mouth_center = (left_mouth + right_mouth) / 2
                mouth_depth = np.linalg.norm(mouth_center - nose) / eye_dist

                # Real faces: nose_depth ~0.3-0.6, mouth_depth ~0.5-0.9
                # Flat photos: ratios are more uniform
                depth_variance = np.std([nose_depth, mouth_depth])

                if depth_variance > 0.08:
                    return 0.8  # Good depth variation
                elif depth_variance > 0.04:
                    return 0.6
                elif depth_variance > 0.02:
                    return 0.4
                return 0.2

            return 0.5

        except Exception as e:
            logger.debug(f'Depth check failed: {e}')
            return 0.5

    def _check_motion(self, face_roi: np.ndarray) -> float:
        """Detect micro-motions (blinks, subtle movements) via frame differencing."""
        try:
            if face_roi is None or face_roi.size == 0:
                return 0.5

            gray = self._to_gray(face_roi)
            if gray is None:
                return 0.5

            # Resize for speed
            small = gray[::4, ::4] if gray.shape[0] > 40 else gray

            self._frame_history.append(small.copy())
            if len(self._frame_history) > self._max_history:
                self._frame_history.pop(0)

            if len(self._frame_history) < 3:
                return 0.5  # Not enough frames yet

            # Compute inter-frame differences
            diffs = []
            for i in range(1, len(self._frame_history)):
                diff = np.mean(np.abs(
                    self._frame_history[i].astype(np.float32) -
                    self._frame_history[i - 1].astype(np.float32)
                ))
                diffs.append(diff)

            mean_diff = np.mean(diffs)

            # Some motion = likely real
            # Zero motion = static photo
            # Too much motion = might be video replay
            if 0.5 < mean_diff < 15:
                return 0.9  # Natural micro-motion
            elif 0.1 < mean_diff <= 0.5:
                return 0.5  # Very slight motion
            elif mean_diff <= 0.1:
                return 0.1  # No motion = static image
            elif mean_diff > 30:
                return 0.4  # Too much = possibly video with artifacts
            return 0.7

        except Exception as e:
            logger.debug(f'Motion check failed: {e}')
            return 0.5

    def _check_colorspace(self, face_roi: np.ndarray) -> float:
        """Check if skin-tone pixels fall within natural YCrCb range."""
        try:
            if face_roi is None or face_roi.size == 0:
                return 0.5

            import cv2
            ycrcb = cv2.cvtColor(face_roi, cv2.COLOR_BGR2YCrCb)

            # Natural skin tone range in YCrCb
            lower = np.array([0, 133, 77], dtype=np.uint8)
            upper = np.array([255, 173, 127], dtype=np.uint8)

            mask = cv2.inRange(ycrcb, lower, upper)
            skin_ratio = np.count_nonzero(mask) / (mask.size + 1e-6)

            # Real faces: 20-70% skin pixels in face ROI
            # Screen photos often have different ratios
            if 0.15 <= skin_ratio <= 0.75:
                return 0.8
            elif 0.08 <= skin_ratio <= 0.85:
                return 0.6
            elif skin_ratio < 0.05:
                return 0.2  # Almost no skin detected
            return 0.4

        except Exception as e:
            logger.debug(f'Colorspace check failed: {e}')
            return 0.5

    @staticmethod
    def _to_gray(img: np.ndarray) -> Optional[np.ndarray]:
        """Convert image to grayscale."""
        try:
            import cv2
            if len(img.shape) == 3:
                return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            return img
        except Exception:
            return None
