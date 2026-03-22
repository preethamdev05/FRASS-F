"""Safe embedding serialization (no pickle)."""

import numpy as np
import struct

EMBEDDING_DIM = 512
EMBEDDING_DTYPE = np.float32


def serialize_embedding(embedding: np.ndarray) -> bytes:
    """Serialize a single embedding to bytes (safe, no pickle)."""
    return embedding.astype(EMBEDDING_DTYPE).tobytes()


def deserialize_embedding(blob: bytes) -> np.ndarray:
    """Deserialize a single embedding from bytes (safe, no pickle)."""
    arr = np.frombuffer(blob, dtype=EMBEDDING_DTYPE).copy()
    if len(arr) != EMBEDDING_DIM:
        raise ValueError(f'Expected embedding of dimension {EMBEDDING_DIM}, got {len(arr)}')
    return arr


def serialize_encodings(encodings: dict[int, list[np.ndarray]]) -> str:
    """Serialize encoding dict to safe binary format."""
    parts = []
    parts.append(struct.pack('I', len(encodings)))
    for student_id, enc_list in encodings.items():
        parts.append(struct.pack('I', student_id))
        parts.append(struct.pack('I', len(enc_list)))
        for enc in enc_list:
            parts.append(enc.astype(EMBEDDING_DTYPE).tobytes())
    return b''.join(parts).decode('latin-1')


def deserialize_encodings(data: str) -> dict[int, list[np.ndarray]] | None:
    """Deserialize encoding dict from safe binary format."""
    try:
        buf = data.encode('latin-1')
        offset = 0

        count = struct.unpack_from('I', buf, offset)[0]
        offset += 4

        result = {}
        for _ in range(count):
            student_id = struct.unpack_from('I', buf, offset)[0]
            offset += 4
            enc_count = struct.unpack_from('I', buf, offset)[0]
            offset += 4

            enc_list = []
            for _ in range(enc_count):
                enc = np.frombuffer(buf, dtype=EMBEDDING_DTYPE, count=EMBEDDING_DIM, offset=offset)
                enc_list.append(enc.copy())
                offset += EMBEDDING_DIM * 4
            result[student_id] = enc_list
        return result
    except Exception:
        return None
