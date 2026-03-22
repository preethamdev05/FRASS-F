"""Embedding quality scoring and face quality checks."""

import numpy as np
from dataclasses import dataclass


@dataclass
class FaceQualityResult:
    blur_score: float
    brightness: float
    resolution_ok: bool
    quality_pass: bool
    reason: str = ''


def embedding_quality(embedding: np.ndarray) -> float:
    """Score embedding quality based on L2 norm deviation.

    High-quality ArcFace embeddings have L2 norm close to 1.0.
    Large deviation indicates poor face crop, blur, or extreme pose.

    Returns:
        Quality score 0.0-1.0 (higher is better)
    """
    norm = np.linalg.norm(embedding)
    return max(0.0, 1.0 - abs(1.0 - norm))


def check_face_quality(face_roi: np.ndarray, min_size: int = 80) -> FaceQualityResult:
    """Check face crop quality: blur, brightness, resolution."""
    try:
        import cv2

        if face_roi is None or face_roi.size == 0:
            return FaceQualityResult(0, 0, False, False, 'Empty face')

        h, w = face_roi.shape[:2]
        if h < min_size or w < min_size:
            return FaceQualityResult(0, 0, False, False, f'Too small ({w}x{h})')

        gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY) if len(face_roi.shape) == 3 else face_roi
        blur = cv2.Laplacian(gray, cv2.CV_64F).var()
        brightness = float(np.mean(gray))

        is_sharp = blur > 50.0
        is_bright = 40 < brightness < 220
        quality_pass = is_sharp and is_bright

        reasons = []
        if not is_sharp:
            reasons.append(f'Blurry ({blur:.0f})')
        if not is_bright:
            reasons.append(f'Poor lighting ({brightness:.0f})')

        return FaceQualityResult(
            blur_score=round(blur, 1),
            brightness=round(brightness, 1),
            resolution_ok=True,
            quality_pass=quality_pass,
            reason='; '.join(reasons) if reasons else 'OK',
        )
    except Exception as e:
        return FaceQualityResult(0, 0, False, False, str(e))
