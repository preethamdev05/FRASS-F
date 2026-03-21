"""Schedule model (configurable class timings)."""

from datetime import datetime, timezone
from app.extensions import db
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy import String, Text


class Schedule(db.Model):
    """Class schedule with configurable days and times."""
    __tablename__ = 'schedules'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(80), nullable=True)
    # Store as comma-separated string for SQLite compat, ARRAY for Postgres
    days_of_week = db.Column(db.Text, nullable=False)  # "0,1,2,3" = Mon-Thu (0=Mon, 6=Sun)
    start_time = db.Column(db.String(5), nullable=False)  # "09:45" (HH:MM)
    end_time = db.Column(db.String(5), nullable=False)    # "10:45"
    late_threshold = db.Column(db.Integer, default=10)     # minutes
    grace_period = db.Column(db.Integer, default=5)        # minutes
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    sessions = db.relationship('AttendanceSession', backref='schedule', lazy='dynamic')

    @property
    def days_list(self):
        """Parse days_of_week string to list of ints."""
        if not self.days_of_week:
            return []
        return [int(d) for d in self.days_of_week.split(',') if d.strip()]

    @days_list.setter
    def days_list(self, value):
        """Set days_of_week from list of ints."""
        self.days_of_week = ','.join(str(d) for d in value)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'department': self.department,
            'days_of_week': self.days_list,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'late_threshold': self.late_threshold,
            'grace_period': self.grace_period,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
