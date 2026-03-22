"""Face alignment using 5-point landmarks (affine transform).

Aligns face to canonical pose before embedding generation.
Improves embedding quality by normalizing face geometry.
"""

import numpy as np
from typing import Optional

# Canonical face landmarks (frontal, 112x112 output)
# Standard reference points for ArcFace alignment
_CANONICAL_LANDMARKS = np.array([
    [38.2946, 51.6963],   # left eye
    [73.5318, 51.5014],   # right eye
    [56.0252, 71.7366],   # nose tip
    [41.5493, 92.3655],   # left mouth corner
    [70.7299, 92.2041],   # right mouth corner
], dtype=np.float64)


def align_face(image: np.ndarray, landmarks: np.ndarray, output_size: tuple = (112, 112)) -> Optional[np.ndarray]:
    """Align a face crop using 5-point landmarks via affine transform.

    Args:
        image: BGR image containing the face
        landmarks: 5x2 array of (x, y) landmark coordinates
            Order: [left_eye, right_eye, nose, left_mouth, right_mouth]
        output_size: Output image size (height, width)

    Returns:
        Aligned face crop, or None if alignment fails
    """
    try:
        import cv2

        if landmarks is None or len(landmarks) < 5:
            return None

        pts = landmarks.astype(np.float64)

        # Ensure we have exactly 5 points
        if pts.shape != (5, 2):
            return None

        # Compute similarity transform from landmarks to canonical
        # Using estimateRigidTransform for robustness
        src = pts[:5].astype(np.float32)
        dst = _CANONICAL_LANDMARKS.astype(np.float32)

        # Scale canonical to output size
        scale_x = output_size[1] / 112.0
        scale_y = output_size[0] / 112.0
        dst_scaled = dst * np.array([scale_x, scale_y], dtype=np.float32)

        # Estimate affine transform
        transform, _ = cv2.estimateAffinePartial2D(src, dst_scaled)
        if transform is None:
            # Fallback: use simple similarity transform
            transform = cv2.getAffineTransform(src[:3], dst_scaled[:3])

        # Apply transform
        aligned = cv2.warpAffine(image, transform, (output_size[1], output_size[0]),
                                  borderMode=cv2.BORDER_REPLICATE)
        return aligned

    except Exception:
        return None


def align_face_simple(image: np.ndarray, bbox: np.ndarray, margin: float = 0.2) -> Optional[np.ndarray]:
    """Simple alignment by cropping with margin (no landmark-based warp).

    Used as fallback when landmarks are not available.
    """
    try:

        h, w = image.shape[:2]
        x1, y1, x2, y2 = bbox.astype(int)

        # Add margin
        bw, bh = x2 - x1, y2 - y1
        mx, my = int(bw * margin), int(bh * margin)
        x1 = max(0, x1 - mx)
        y1 = max(0, y1 - my)
        x2 = min(w, x2 + mx)
        y2 = min(h, y2 + my)

        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        return crop
    except Exception:
        return None
