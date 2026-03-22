"""Tests for fras_core shared package."""

import numpy as np
from fras_core.quality import embedding_quality, check_face_quality
from fras_core.serialization import serialize_embedding, deserialize_embedding, serialize_encodings, deserialize_encodings
from fras_core.alignment import align_face_simple


def test_embedding_quality_perfect():
    emb = np.random.randn(512).astype(np.float32)
    emb = emb / np.linalg.norm(emb)
    quality = embedding_quality(emb)
    assert quality > 0.99


def test_embedding_quality_poor():
    emb = np.zeros(512, dtype=np.float32)
    quality = embedding_quality(emb)
    assert quality == 0.0


def test_embedding_quality_scaled():
    emb = np.random.randn(512).astype(np.float32)
    emb = emb / np.linalg.norm(emb) * 2.0
    quality = embedding_quality(emb)
    assert quality < 0.5


def test_serialize_deserialize_embedding():
    emb = np.random.randn(512).astype(np.float32)
    blob = serialize_embedding(emb)
    recovered = deserialize_embedding(blob)
    np.testing.assert_array_almost_equal(emb, recovered)


def test_serialize_deserialize_dict():
    encodings = {
        10: [np.random.randn(512).astype(np.float32)],
        20: [np.random.randn(512).astype(np.float32)] * 3,
    }
    serialized = serialize_encodings(encodings)
    deserialized = deserialize_encodings(serialized)
    assert set(deserialized.keys()) == {10, 20}
    assert len(deserialized[20]) == 3


def test_align_face_simple():
    image = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
    bbox = np.array([50, 50, 150, 150], dtype=np.float64)
    result = align_face_simple(image, bbox, margin=0.1)
    assert result is not None
    assert result.shape[0] > 0
    assert result.shape[1] > 0


def test_align_face_simple_out_of_bounds():
    image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    bbox = np.array([0, 0, 100, 100], dtype=np.float64)
    result = align_face_simple(image, bbox, margin=0.2)
    assert result is not None


def test_check_face_quality_random():
    face = np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8)
    result = check_face_quality(face)
    assert result.blur_score > 0
    assert result.brightness > 0
