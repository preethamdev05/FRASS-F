"""Tests for ML anti-spoofing module."""

import numpy as np
from app.services.antispoof import AntiSpoofDetector, fuse_liveness_scores


def test_antispoof_available_without_model():
    det = AntiSpoofDetector(model_path='')
    assert not det.available


def test_antispoof_predict_returns_negative_without_model():
    det = AntiSpoofDetector(model_path='')
    face = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    score = det.predict(face)
    assert score == -1.0


def test_fuse_ml_dominant():
    result = fuse_liveness_scores(0.9, 0.3, alpha=0.6)
    expected = 0.6 * 0.9 + 0.4 * 0.3
    assert abs(result - expected) < 0.001


def test_fuse_heuristic_only():
    result = fuse_liveness_scores(-1.0, 0.7, alpha=0.6)
    assert result == 0.7


def test_fuse_equal_weight():
    result = fuse_liveness_scores(0.8, 0.6, alpha=0.5)
    expected = 0.5 * 0.8 + 0.5 * 0.6
    assert abs(result - expected) < 0.001
