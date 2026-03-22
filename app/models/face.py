"""Face encoding model with pgvector support."""

from datetime import datetime, timezone
from app.extensions import db


class FaceEncoding(db.Model):
    __tablename__ = 'face_encodings'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    encoding_blob = db.Column(db.LargeBinary, nullable=False)  # numpy.tobytes() safe format
    photo_path = db.Column(db.String(512), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # pgvector column (PostgreSQL only — NULL on SQLite)
    # Populated by migration or trigger; stores the same embedding as encoding_blob
    # but in pgvector format for O(log n) ANN search via HNSW index
    # embedding_vector = db.Column(Vector(512), nullable=True)  # requires pgvector extension

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'photo_path': self.photo_path,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
