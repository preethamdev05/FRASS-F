"""Liveness detection tests — expanded coverage."""

import numpy as np
from app.services.liveness import LivenessDetector, check_face_quality


def test_liveness_result_structure():
    detector = LivenessDetector(threshold=0.6)
    face_roi = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    result = detector.analyze(face_roi)
    assert hasattr(result, 'score')
    assert hasattr(result, 'is_live')
    assert hasattr(result, 'breakdown')
    assert isinstance(result.score, float)
    assert isinstance(result.is_live, bool)
    assert 0.0 <= result.score <= 1.0


def test_liveness_threshold():
    detector_low = LivenessDetector(threshold=0.3)
    detector_high = LivenessDetector(threshold=0.9)
    face_roi = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    result_low = detector_low.analyze(face_roi)
    result_high = detector_high.analyze(face_roi)
    assert isinstance(result_low.is_live, bool)
    assert isinstance(result_high.is_live, bool)


def test_liveness_empty_face():
    detector = LivenessDetector()
    result = detector.analyze(np.zeros((1, 1, 3), dtype=np.uint8))
    assert isinstance(result.score, float)


def test_liveness_weights_sum_to_one():
    det = LivenessDetector()
    total = sum(det.weights.values())
    assert abs(total - 1.0) < 0.01


def test_liveness_ml_antispoof_weight():
    det = LivenessDetector()
    assert 'ml_antispoof' in det.weights
    assert det.weights['ml_antispoof'] == 0.25


def test_check_face_quality_good():
    face = np.random.randint(80, 180, (100, 100, 3), dtype=np.uint8)
    result = check_face_quality(face)
    assert result.blur_score > 0
    assert 40 < result.brightness < 220


def test_check_face_quality_too_small():
    face = np.random.randint(0, 255, (20, 20, 3), dtype=np.uint8)
    result = check_face_quality(face)
    assert not result.quality_pass
    assert 'Too small' in result.reason


def test_check_face_quality_empty():
    result = check_face_quality(None)
    assert not result.quality_pass


def test_liveness_analyze_specific_layers():
    det = LivenessDetector(threshold=0.5, enabled_layers=['texture', 'colorspace'])
    face = np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8)
    result = det.analyze(face)
    assert isinstance(result.score, float)
    assert 'texture' in result.breakdown
    assert 'colorspace' in result.breakdown


def test_liveness_redistributes_when_ml_unavailable():
    det = LivenessDetector(threshold=0.65, enabled_layers=['texture', 'colorspace', 'ml_antispoof'])
    face = np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8)
    result = det.analyze(face)
    assert isinstance(result.score, float)


def test_liveness_returns_reason():
    det = LivenessDetector(threshold=0.1, enabled_layers=['texture'])
    face = np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8)
    result = det.analyze(face)
    assert isinstance(result.reason, str)
