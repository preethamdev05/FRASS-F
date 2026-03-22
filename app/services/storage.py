"""Storage abstraction for face images and assets."""

import os
import shutil
import logging

logger = logging.getLogger(__name__)


class StorageService:
    """Abstract file storage operations for face images."""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir

    def ensure_dir(self, *path_parts: str) -> str:
        """Create directory if it doesn't exist."""
        path = os.path.join(self.base_dir, *path_parts)
        os.makedirs(path, exist_ok=True)
        return path

    def save_image(self, student_sid: str, filename: str, image_bytes: bytes) -> str:
        """Save an image file and return its path."""
        student_dir = self.ensure_dir(student_sid)
        filepath = os.path.join(student_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(image_bytes)
        return filepath

    def delete_student_dir(self, student_sid: str) -> bool:
        """Delete all stored files for a student."""
        student_dir = os.path.join(self.base_dir, student_sid)
        if os.path.isdir(student_dir):
            shutil.rmtree(student_dir, ignore_errors=True)
            return True
        return False

    def list_student_files(self, student_sid: str) -> list[str]:
        """List files for a student."""
        student_dir = os.path.join(self.base_dir, student_sid)
        if not os.path.isdir(student_dir):
            return []
        return [os.path.join(student_dir, f) for f in os.listdir(student_dir)]
