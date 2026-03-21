"""Face encoding model."""

from datetime import datetime, timezone
from app.extensions import db


class FaceEncoding(db.Model):
    __tablename__ = 'face_encodings'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    encoding_blob = db.Column(db.LargeBinary, nullable=False)  # numpy array bytes
    photo_path = db.Column(db.String(512), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'photo_path': self.photo_path,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
