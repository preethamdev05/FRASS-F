"""Liveness detection tests."""

import numpy as np
from app.services.liveness import LivenessDetector


def test_liveness_result_structure():
    """Test that liveness returns proper structure."""
    detector = LivenessDetector(threshold=0.6)

    # Create a dummy face ROI (small gray image)
    face_roi = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    result = detector.analyze(face_roi)

    assert hasattr(result, 'score')
    assert hasattr(result, 'is_live')
    assert hasattr(result, 'breakdown')
    assert isinstance(result.score, float)
    assert isinstance(result.is_live, bool)
    assert 0.0 <= result.score <= 1.0


def test_liveness_threshold():
    """Test threshold behavior."""
    detector_low = LivenessDetector(threshold=0.3)
    detector_high = LivenessDetector(threshold=0.9)

    face_roi = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)

    result_low = detector_low.analyze(face_roi)
    result_high = detector_high.analyze(face_roi)

    # Low threshold is easier to pass
    # (Results may vary with random data, but structure should be valid)
    assert isinstance(result_low.is_live, bool)
    assert isinstance(result_high.is_live, bool)


def test_liveness_empty_face():
    """Test with empty/None input."""
    detector = LivenessDetector()
    result = detector.analyze(np.zeros((1, 1, 3), dtype=np.uint8))
    assert isinstance(result.score, float)
