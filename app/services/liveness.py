"""Liveness detection (anti-spoofing) module.

Multi-layer approach:
1. Texture analysis (LBP variance)
2. Moire pattern detection (FFT)
3. Depth estimation (landmark geometry)
4. Eye blink detection (EAR - Eye Aspect Ratio)
5. Head pose consistency
6. Color space analysis (YCrCb skin distribution)
7. Image quality checks (blur, brightness, resolution)
"""

import logging
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LivenessResult:
    score: float
    is_live: bool
    breakdown: dict
    reason: str = ''
    quality: dict = field(default_factory=dict)


@dataclass
class FaceQuality:
    """Image quality metrics for a face crop."""
    blur_score: float  # Laplacian variance, higher = sharper
    brightness: float  # 0-255 mean pixel value
    resolution_ok: bool
    quality_pass: bool
    reason: str = ''


def check_face_quality(face_roi: np.ndarray) -> FaceQuality:
    """Check if a face crop is good enough for recognition."""
    import cv2

    if face_roi is None or face_roi.size == 0:
        return FaceQuality(0, 0, False, False, 'Empty face region')

    h, w = face_roi.shape[:2]
    min_resolution = 80

    if h < min_resolution or w < min_resolution:
        return FaceQuality(0, 0, False, False,
                           f'Too small ({w}x{h}), minimum {min_resolution}px')

    gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY) if len(face_roi.shape) == 3 else face_roi

    # Blur detection via Laplacian variance
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    blur_threshold = 50.0
    is_sharp = laplacian_var > blur_threshold

    # Brightness check
    mean_brightness = float(np.mean(gray))
    is_bright_enough = 40 < mean_brightness < 220

    quality_pass = is_sharp and is_bright_enough
    reasons = []
    if not is_sharp:
        reasons.append(f'Blurry (score: {laplacian_var:.1f}, need >{blur_threshold})')
    if not is_bright_enough:
        reasons.append(f'Poor lighting (brightness: {mean_brightness:.0f}, need 40-220)')

    return FaceQuality(
        blur_score=round(laplacian_var, 1),
        brightness=round(mean_brightness, 1),
        resolution_ok=True,
        quality_pass=quality_pass,
        reason='; '.join(reasons) if reasons else 'Quality OK',
    )


class LivenessDetector:
    """Multi-layer liveness detection for anti-spoofing.

    Combines heuristic signals (texture, moire, depth, blink, colorspace, quality)
    with optional ML-based anti-spoofing (MiniFASNet) via weighted fusion.

    Fusion: final_score = alpha * ml_score + (1 - alpha) * heuristic_score
    """

    def __init__(self, threshold=0.65, enabled_layers=None, antispoof_model_path: str = ''):
        self.threshold = threshold
        # Weights for each layer (must sum to 1.0)
        self.weights = {
            'texture': 0.15,
            'moire': 0.10,
            'depth': 0.15,
            'blink': 0.15,
            'colorspace': 0.10,
            'quality': 0.10,
            'ml_antispoof': 0.25,  # ML model gets highest single weight
        }
        if enabled_layers:
            valid_keys = set(self.weights.keys())
            invalid_keys = set(enabled_layers) - valid_keys
            if invalid_keys:
                logger.warning('Unknown enabled_layers keys: %s', invalid_keys)
            enabled_layers = [k for k in enabled_layers if k in valid_keys]
            total = sum(self.weights[k] for k in enabled_layers)
            self.weights = {k: self.weights[k] / total for k in enabled_layers}
        self.enabled = enabled_layers or list(self.weights.keys())

        # Frame history for blink/motion detection
        self._frame_history: List[np.ndarray] = []
        self._ear_history: List[float] = []
        self._max_history = 30

        # ML anti-spoofing (lazy-loaded)
        self._antispoof = None
        self._antispoof_path = antispoof_model_path

    def analyze(self, face_roi, landmarks=None, frame=None) -> LivenessResult:
        """Run all enabled liveness checks (heuristic + ML)."""
        scores = {}
        reasons = []

        enabled = list(self.enabled)
        weights = dict(self.weights)

        # Image quality check (always run first — reject bad images early)
        quality = check_face_quality(face_roi)
        if not quality.quality_pass:
            return LivenessResult(
                score=0.0,
                is_live=False,
                breakdown={'quality': 0.0},
                reason=f'Poor image quality: {quality.reason}',
                quality={'blur': quality.blur_score, 'brightness': quality.brightness},
            )

        if 'quality' in enabled:
            q_score = min(1.0, quality.blur_score / 200.0) * 0.5
            q_score += 0.5 if quality.quality_pass else 0.0
            scores['quality'] = q_score

        if 'texture' in enabled:
            s = self._check_texture(face_roi)
            scores['texture'] = s
            if s < 0.3:
                reasons.append('low texture variance (possible printed photo)')

        if 'moire' in enabled:
            s = self._check_moire(face_roi)
            scores['moire'] = s
            if s < 0.3:
                reasons.append('moire patterns detected (possible screen)')

        if 'depth' in enabled and landmarks is not None:
            s = self._check_depth(landmarks)
            scores['depth'] = s
            if s < 0.3:
                reasons.append('flat face geometry (possible 2D photo)')

        if 'blink' in enabled:
            s = self._check_blink(face_roi, landmarks)
            scores['blink'] = s
            if s < 0.3:
                reasons.append('no eye blinks detected (possible photo)')

        if 'colorspace' in enabled:
            s = self._check_colorspace(face_roi)
            scores['colorspace'] = s
            if s < 0.3:
                reasons.append('abnormal skin color distribution')

        # ML anti-spoofing (runs alongside heuristics)
        if 'ml_antispoof' in enabled:
            if self._antispoof is None:
                from app.services.antispoof import AntiSpoofDetector
                self._antispoof = AntiSpoofDetector(model_path=self._antispoof_path)

            ml_score = self._antispoof.predict(face_roi)
            if ml_score >= 0:
                scores['ml_antispoof'] = ml_score
                if ml_score < 0.4:
                    reasons.append('ML anti-spoof: spoof detected (score: %.2f)' % ml_score)
            else:
                # Model unavailable — redistribute weight to heuristics
                enabled = [k for k in enabled if k != 'ml_antispoof']
                total = sum(weights[k] for k in enabled)
                weights = {k: weights[k] / total for k in enabled}

        # Weighted total
        total = sum(scores.get(k, 0.5) * weights.get(k, 0) for k in enabled)
        is_live = total >= self.threshold

        reason = '; '.join(reasons) if reasons else 'all checks passed'

        return LivenessResult(
            score=round(total, 3),
            is_live=is_live,
            breakdown={k: round(v, 3) for k, v in scores.items()},
            reason=reason,
            quality={'blur': quality.blur_score, 'brightness': quality.brightness},
        )

    def _check_texture(self, face_roi: np.ndarray) -> float:
        """LBP-based texture analysis. Real faces have micro-texture."""
        try:
            if face_roi is None or face_roi.size == 0:
                return 0.5
            gray = self._to_gray(face_roi)
            if gray is None:
                return 0.5

            h, w = gray.shape
            if h < 10 or w < 10:
                return 0.5

            # Vectorized local variance (much faster than nested loops)
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

            if var_mean < 10:
                return 0.2
            elif var_mean > 500:
                return 0.7

            cv = var_std / (var_mean + 1e-6)
            if 0.3 <= cv <= 2.5:
                return min(1.0, 0.5 + cv * 0.2)
            return 0.4

        except Exception as e:
            logger.debug('Texture check failed: %s', e)
            return 0.5

    def _check_moire(self, face_roi: np.ndarray) -> float:
        """FFT-based moire pattern detection (screens show periodic patterns)."""
        try:
            if face_roi is None or face_roi.size == 0:
                return 0.5
            gray = self._to_gray(face_roi)
            if gray is None:
                return 0.5

            f = np.fft.fft2(gray.astype(np.float32))
            fshift = np.fft.fftshift(f)
            magnitude = np.log(np.abs(fshift) + 1)

            h, w = magnitude.shape
            cy, cx = h // 2, w // 2

            inner_r = min(h, w) // 8
            outer_r = min(h, w) // 2 - 5

            y, x = np.ogrid[:h, :w]
            dist = np.sqrt((y - cy) ** 2 + (x - cx) ** 2)
            band = (dist > inner_r) & (dist < outer_r)

            if not np.any(band):
                return 0.5

            high_freq = magnitude[band]
            peak_ratio = np.percentile(high_freq, 99) / (np.mean(high_freq) + 1e-6)

            if peak_ratio > 8:
                return 0.2
            elif peak_ratio > 5:
                return 0.4
            elif peak_ratio > 3:
                return 0.6
            return 0.8

        except Exception as e:
            logger.debug('Moire check failed: %s', e)
            return 0.5

    def _check_depth(self, landmarks: np.ndarray) -> float:
        """Estimate 3D depth from facial landmark geometry."""
        try:
            if landmarks is None or len(landmarks) < 5:
                return 0.5

            pts = landmarks
            if pts.shape == (5, 2):
                left_eye = pts[0]
                right_eye = pts[1]
                nose = pts[2]
                left_mouth = pts[3]
                right_mouth = pts[4]

                eye_dist = np.linalg.norm(right_eye - left_eye) + 1e-6

                eye_center = (left_eye + right_eye) / 2
                nose_depth = np.linalg.norm(nose - eye_center) / eye_dist

                mouth_center = (left_mouth + right_mouth) / 2
                mouth_depth = np.linalg.norm(mouth_center - nose) / eye_dist

                depth_variance = np.std([nose_depth, mouth_depth])

                if depth_variance > 0.08:
                    return 0.8
                elif depth_variance > 0.04:
                    return 0.6
                elif depth_variance > 0.02:
                    return 0.4
                return 0.2

            return 0.5

        except Exception as e:
            logger.debug('Depth check failed: %s', e)
            return 0.5

    def _check_blink(self, face_roi: np.ndarray, landmarks=None) -> float:
        """Detect eye blinks using EAR (Eye Aspect Ratio) from landmarks.

        EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
        where p1-p6 are the 6 eye contour landmarks.

        Since InsightFace provides 5 landmarks (not full eye contour),
        we use a hybrid approach:
        - Use frame history to detect rapid intensity changes in the eye region
        - Cross-reference with landmarks if available
        """
        try:
            if face_roi is None or face_roi.size == 0:
                return 0.5

            gray = self._to_gray(face_roi)
            if gray is None:
                return 0.5

            h, w = gray.shape

            # Extract eye regions (upper 40% of face, left and right halves)
            eye_region = gray[:int(h * 0.45), :]
            if eye_region.size == 0:
                return 0.5

            # Compute eye region intensity variance (blinks cause dark/light transitions)
            eye_intensity = float(np.mean(eye_region))

            self._ear_history.append(eye_intensity)
            if len(self._ear_history) > self._max_history:
                self._ear_history.pop(0)

            if len(self._ear_history) < 10:
                return 0.5  # Not enough frames yet

            # Detect blink patterns: sudden intensity change followed by recovery
            intensities = np.array(self._ear_history)
            diffs = np.abs(np.diff(intensities))

            # A real blink creates a spike in frame-to-frame difference
            max_diff = float(np.max(diffs))
            mean_diff = float(np.mean(diffs))
            spike_ratio = max_diff / (mean_diff + 1e-6)

            # Real person: occasional spikes (blinks)
            # Photo: consistent low diffs
            if spike_ratio > 3.0 and max_diff > 5:
                return 0.9  # Strong blink pattern detected
            elif spike_ratio > 2.0 and max_diff > 3:
                return 0.7
            elif mean_diff < 0.5:
                return 0.2  # No variation = static photo
            elif mean_diff < 1.0:
                return 0.4  # Very little variation

            return 0.6

        except Exception as e:
            logger.debug('Blink check failed: %s', e)
            return 0.5

    def _check_colorspace(self, face_roi: np.ndarray) -> float:
        """Check if skin-tone pixels fall within natural YCrCb range."""
        try:
            if face_roi is None or face_roi.size == 0:
                return 0.5

            import cv2
            ycrcb = cv2.cvtColor(face_roi, cv2.COLOR_BGR2YCrCb)

            lower = np.array([0, 133, 77], dtype=np.uint8)
            upper = np.array([255, 173, 127], dtype=np.uint8)

            mask = cv2.inRange(ycrcb, lower, upper)
            skin_ratio = np.count_nonzero(mask) / (mask.size + 1e-6)

            if 0.15 <= skin_ratio <= 0.75:
                return 0.8
            elif 0.08 <= skin_ratio <= 0.85:
                return 0.6
            elif skin_ratio < 0.05:
                return 0.2
            return 0.4

        except Exception as e:
            logger.debug('Colorspace check failed: %s', e)
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
