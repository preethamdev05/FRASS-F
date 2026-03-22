"""Attendance business logic."""

import logging
from datetime import datetime, timezone, date, timedelta, time
from typing import Optional

from app.extensions import db
from app.models.attendance import AttendanceRecord, AttendanceSession
from app.models.student import Student
from app.models.schedule import Schedule
from app.realtime.events import broadcast_student_marked, broadcast_stats_update

logger = logging.getLogger(__name__)


def start_session(user_id: int, schedule_id: int = None, tolerance: float = 0.5) -> AttendanceSession:
    """Start a new attendance session."""
    # End any existing active sessions for this user
    active = AttendanceSession.query.filter_by(started_by=user_id, status='active').all()
    for s in active:
        s.status = 'ended'
        s.ended_at = datetime.now(timezone.utc)

    session = AttendanceSession(
        started_by=user_id,
        schedule_id=schedule_id,
        tolerance=tolerance,
        status='active',
    )
    db.session.add(session)
    db.session.commit()

    # Load face encodings
    from app.services.engine import get_face_engine
    engine = get_face_engine()
    engine.load_all_encodings()

    total = Student.query.filter_by(is_active=True).count()
    logger.info(f'Session {session.id} started by user {user_id}, {total} students registered')
    return session


def stop_session(session_id: int) -> AttendanceSession:
    """End an attendance session."""
    session = db.session.get(AttendanceSession, session_id)
    if session:
        session.status = 'ended'
        session.ended_at = datetime.now(timezone.utc)
        db.session.commit()
    return session


def get_active_session() -> Optional[AttendanceSession]:
    """Get the currently active session."""
    return AttendanceSession.query.filter_by(status='active').first()


def mark_attendance(student_db_id: int, session_id: int, confidence: float,
                    method: str = 'face', liveness_score: float = None) -> dict:
    """Mark a student as present."""
    session = db.session.get(AttendanceSession, session_id)
    if not session or session.status != 'active':
        return {'error': 'No active session'}

    now = datetime.now(timezone.utc)
    today = date.today()

    # Determine status based on schedule
    status = 'present'
    schedule = session.schedule if session.schedule_id else None
    if schedule:
        status = _compute_status(schedule, now)

    # Check if already marked
    existing = AttendanceRecord.query.filter_by(
        student_id=student_db_id, session_id=session_id
    ).first()

    if existing:
        return {'status': 'already_marked', 'record': existing.to_dict()}

    record = AttendanceRecord(
        student_id=student_db_id,
        session_id=session_id,
        date=today,
        time_in=now,
        status=status,
        confidence=confidence,
        method=method,
        liveness_score=liveness_score,
    )
    db.session.add(record)
    db.session.commit()

    student = db.session.get(Student, student_db_id)
    result = {
        'status': 'marked',
        'record': record.to_dict(),
        'name': student.name if student else 'Unknown',
        'student_id': student.student_id if student else 'Unknown',
    }

    # Broadcast via WebSocket
    broadcast_student_marked(session_id, result)

    # Update dashboard stats
    stats = get_today_stats()
    broadcast_stats_update(stats)

    return result


def mark_manual(student_db_id: int, notes: str = None) -> dict:
    """Manually mark attendance (no active session required)."""
    today = date.today()
    now = datetime.now(timezone.utc)

    # Check for active session
    session = get_active_session()
    session_id = session.id if session else None

    # Check if already marked today
    existing = AttendanceRecord.query.filter_by(
        student_id=student_db_id, date=today
    ).first()

    if existing:
        return {'error': 'Already marked today', 'record': existing.to_dict()}

    # Determine status from schedules
    status = 'present'
    schedule = Schedule.query.filter_by(is_active=True).first()
    if schedule:
        status = _compute_status(schedule, now)

    record = AttendanceRecord(
        student_id=student_db_id,
        session_id=session_id,
        date=today,
        time_in=now,
        status=status,
        method='manual',
        notes=notes,
    )
    db.session.add(record)
    db.session.commit()

    return {'status': 'marked', 'record': record.to_dict_with_student()}


def _compute_status(schedule: Schedule, marked_time: datetime) -> str:
    """Compute attendance status based schedule."""
    # Parse schedule start time
    try:
        parts = schedule.start_time.split(':')
        start_time = time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return 'present'

    start_dt = datetime.combine(marked_time.date(), start_time, tzinfo=timezone.utc)
    late_dt = start_dt + timedelta(minutes=schedule.late_threshold)

    if marked_time <= late_dt:
        return 'present'
    elif marked_time <= late_dt + timedelta(minutes=schedule.grace_period):
        return 'late'
    return 'late'


def get_today_attendance() -> list:
    """Get today's attendance records."""
    today = date.today()
    records = AttendanceRecord.query.filter_by(date=today)\
        .join(Student).order_by(AttendanceRecord.time_in).all()
    return [r.to_dict_with_student() for r in records]


def get_today_stats() -> dict:
    """Get today's attendance statistics."""
    today = date.today()
    total_students = Student.query.filter_by(is_active=True).count()

    records = AttendanceRecord.query.filter_by(date=today).all()
    present = sum(1 for r in records if r.status == 'present')
    late = sum(1 for r in records if r.status == 'late')
    total_marked = present + late

    rate = round((total_marked / total_students * 100), 1) if total_students > 0 else 0

    return {
        'total_students': total_students,
        'present': present,
        'late': late,
        'absent': total_students - total_marked,
        'total_marked': total_marked,
        'rate': rate,
    }


def get_attendance_range(start_date, end_date, student_db_id=None) -> list:
    """Get attendance records for a date range."""
    query = AttendanceRecord.query.join(Student)\
        .filter(AttendanceRecord.date >= start_date, AttendanceRecord.date <= end_date)

    if student_db_id:
        query = query.filter(AttendanceRecord.student_id == student_db_id)

    records = query.order_by(AttendanceRecord.date.desc(), AttendanceRecord.time_in).all()
    return [r.to_dict_with_student() for r in records]


def get_dashboard_data() -> dict:
    """Get all dashboard data."""
    today = date.today()
    total_students = Student.query.filter_by(is_active=True).count()

    records = AttendanceRecord.query.filter_by(date=today).all()
    present = sum(1 for r in records if r.status == 'present')
    late = sum(1 for r in records if r.status == 'late')
    rate = round((present + late) / total_students * 100, 1) if total_students > 0 else 0

    # Department stats
    dept_stats = {}
    for r in records:
        dept = r.student.department or 'Unassigned'
        if dept not in dept_stats:
            dept_stats[dept] = {'total': 0, 'present': 0}
        dept_stats[dept]['present'] += 1

    # Count total per dept
    all_students = Student.query.filter_by(is_active=True).all()
    for s in all_students:
        dept = s.department or 'Unassigned'
        if dept not in dept_stats:
            dept_stats[dept] = {'total': 0, 'present': 0}
        dept_stats[dept]['total'] += 1

    # Week trend
    week_trend = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        day_records = AttendanceRecord.query.filter_by(date=d).all()
        day_present = sum(1 for r in day_records if r.status in ('present', 'late'))
        week_trend.append({'date': d.isoformat(), 'present': day_present, 'count': len(day_records)})

    return {
        'total_students': total_students,
        'present_today': present,
        'late_today': late,
        'absent_today': total_students - present - late,
        'attendance_rate_today': rate,
        'department_stats': [{'department': k, 'present': v['present'], 'total': v['total']}
                             for k, v in dept_stats.items()],
        'week_trend': week_trend,
    }
