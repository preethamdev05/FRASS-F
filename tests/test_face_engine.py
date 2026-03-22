"""Tests for face engine core."""

import numpy as np
from fras_core.serialization import serialize_embedding as _serialize_single_encoding
from app.services.face_engine import (
    _deserialize_single_encoding,
    _serialize_encodings,
    _deserialize_encodings,
    EMBEDDING_DIM,
)


def test_serialize_deserialize_roundtrip():
    original = np.random.randn(EMBEDDING_DIM).astype(np.float32)
    blob = _serialize_single_encoding(original)
    recovered = _deserialize_single_encoding(blob)
    np.testing.assert_array_almost_equal(original, recovered)


def test_serialize_deserialize_dict():
    encodings = {
        1: [np.random.randn(EMBEDDING_DIM).astype(np.float32)],
        2: [np.random.randn(EMBEDDING_DIM).astype(np.float32),
            np.random.randn(EMBEDDING_DIM).astype(np.float32)],
    }
    serialized = _serialize_encodings(encodings)
    deserialized = _deserialize_encodings(serialized)

    assert 1 in deserialized
    assert 2 in deserialized
    assert len(deserialized[1]) == 1
    assert len(deserialized[2]) == 2

    np.testing.assert_array_almost_equal(encodings[1][0], deserialized[1][0])
    np.testing.assert_array_almost_equal(encodings[2][1], deserialized[2][1])


def test_serialize_empty_dict():
    serialized = _serialize_encodings({})
    deserialized = _deserialize_encodings(serialized)
    assert deserialized == {}


def test_deserialize_invalid_data():
    result = _deserialize_encodings('invalid')
    assert result is None
