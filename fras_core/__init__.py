"""FRAS Core — shared face recognition library.

Used by monolith, IoT backend, and edge devices.
Provides: alignment, batch inference, embedding quality, serialization.
"""

from fras_core.alignment import align_face
from fras_core.quality import embedding_quality, check_face_quality
from fras_core.batch import batch_detect_and_encode
from fras_core.serialization import serialize_embedding, deserialize_embedding

__all__ = [
    'align_face',
    'embedding_quality',
    'check_face_quality',
    'batch_detect_and_encode',
    'serialize_embedding',
    'deserialize_embedding',
]
