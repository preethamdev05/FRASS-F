"""Batch face detection and encoding for multi-face frames.

Processes all faces in a single InsightFace forward pass when possible,
significantly faster than per-face processing for frames with multiple faces.
"""

import numpy as np


def batch_detect_and_encode(detector, frame: np.ndarray, align_fn=None) -> list:
    """Detect all faces in frame and generate aligned embeddings.

    Args:
        detector: InsightFace FaceAnalysis instance
        frame: BGR image
        align_fn: Optional alignment function (landmarks -> aligned crop)

    Returns:
        List of dicts with keys: bbox, landmarks, embedding, aligned_face
    """
    try:
        faces = detector.get(frame)
    except Exception:
        return []

    results = []
    for face in faces:
        try:
            embedding = face.normed_embedding
            if embedding is None:
                continue

            bbox = face.bbox.astype(int)
            landmarks = face.kps if hasattr(face, 'kps') else None

            result = {
                'bbox': bbox,
                'landmarks': landmarks,
                'embedding': embedding,
                'face': face,
            }

            # Optional alignment
            if align_fn and landmarks is not None:
                aligned = align_fn(frame, landmarks)
                if aligned is not None:
                    result['aligned_face'] = aligned

            results.append(result)
        except Exception:
            continue

    return results
