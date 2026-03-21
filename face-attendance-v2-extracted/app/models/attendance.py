"""Attendance models (records + sessions)."""

from datetime import datetime, timezone
from app.extensions import db


class AttendanceSession(db.Model):
    """A single attendance-taking session (teacher opens, teacher closes)."""
    __tablename__ = 'attendance_sessions'

    id = db.Column(db.Integer, primary_key=True)
    started_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedules.id'), nullable=True)
    tolerance = db.Column(db.Float, default=0.5)
    status = db.Column(db.String(20), default='active')  # active, ended
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    records = db.relationship('AttendanceRecord', backref='session', lazy='dynamic')
    starter = db.relationship('User', backref='sessions_started')

    def to_dict(self):
        return {
            'id': self.id,
            'started_by': self.started_by,
            'schedule_id': self.schedule_id,
            'tolerance': self.tolerance,
            'status': self.status,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'record_count': self.records.count(),
        }


class AttendanceRecord(db.Model):
    """Individual attendance mark for a student."""
    __tablename__ = 'attendance_records'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey('attendance_sessions.id'), nullable=True, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    time_in = db.Column(db.DateTime, nullable=False)
    time_out = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='present')  # present, late, absent, excused
    confidence = db.Column(db.Float, nullable=True)
    method = db.Column(db.String(20), default='face')  # face, manual
    liveness_score = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Unique constraint: one record per student per session
    __table_args__ = (
        db.UniqueConstraint('student_id', 'session_id', name='uq_student_session'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'session_id': self.session_id,
            'date': self.date.isoformat() if self.date else None,
            'time_in': self.time_in.isoformat() if self.time_in else None,
            'time_out': self.time_out.isoformat() if self.time_out else None,
            'status': self.status,
            'confidence': self.confidence,
            'method': self.method,
            'liveness_score': self.liveness_score,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def to_dict_with_student(self):
        d = self.to_dict()
        if self.student:
            d['name'] = self.student.name
            d['sid'] = self.student.student_id
            d['department'] = self.student.department
        return d
