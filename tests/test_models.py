"""Model unit tests."""

import json
from datetime import datetime, timezone, timedelta, date


from app.extensions import db
from app.models.user import User
from app.models.student import Student
from app.models.attendance import AttendanceRecord, AttendanceSession
from app.models.schedule import Schedule
from app.models.audit import AuditLog
from app.models.face import FaceEncoding


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------

class TestUserModel:
    def test_set_and_check_password(self, app):
        with app.app_context():
            user = User(username='pwtest', role='teacher')
            user.set_password('MySecret123')
            assert user.password_hash != 'MySecret123'
            assert user.check_password('MySecret123') is True

    def test_check_password_wrong(self, app):
        with app.app_context():
            user = User(username='pwtest2', role='teacher')
            user.set_password('CorrectPass1')
            assert user.check_password('WrongPass') is False

    def test_to_dict(self, app):
        with app.app_context():
            user = User(username='dictuser', email='a@b.com', role='admin')
            user.set_password('Pass1234')
            db.session.add(user)
            db.session.commit()
            d = user.to_dict()
            assert d['username'] == 'dictuser'
            assert d['email'] == 'a@b.com'
            assert d['role'] == 'admin'
            assert 'id' in d
            assert 'created_at' in d
            assert 'password_hash' not in d

    def test_is_locked_not_locked(self, app):
        with app.app_context():
            user = User(username='unlocked', role='teacher')
            user.set_password('Pass1234')
            assert user.is_locked() is False

    def test_is_locked_active_lock(self, app):
        with app.app_context():
            user = User(username='locked', role='teacher')
            user.set_password('Pass1234')
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)
            assert user.is_locked() is True

    def test_is_locked_expired_lock(self, app):
        with app.app_context():
            user = User(username='expired', role='teacher')
            user.set_password('Pass1234')
            user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=5)
            user.failed_login_attempts = 5
            assert user.is_locked() is False
            assert user.failed_login_attempts == 0

    def test_record_failed_login(self, app):
        with app.app_context():
            user = User(username='fluser', role='teacher')
            user.set_password('Pass1234')
            db.session.add(user)
            db.session.commit()
            user.record_failed_login(max_attempts=3, lockout_seconds=300)
            assert user.failed_login_attempts == 1

    def test_record_failed_login_locks(self, app):
        with app.app_context():
            user = User(username='fllock', role='teacher')
            user.set_password('Pass1234')
            db.session.add(user)
            db.session.commit()
            for _ in range(5):
                user.record_failed_login(max_attempts=5, lockout_seconds=300)
            assert user.locked_until is not None
            assert user.is_locked() is True

    def test_record_successful_login(self, app):
        with app.app_context():
            user = User(username='succuser', role='teacher')
            user.set_password('Pass1234')
            db.session.add(user)
            db.session.commit()
            user.failed_login_attempts = 3
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)
            user.record_successful_login()
            assert user.failed_login_attempts == 0
            assert user.locked_until is None


# ---------------------------------------------------------------------------
# Student model
# ---------------------------------------------------------------------------

class TestStudentModel:
    def _make_student(self):
        return Student(
            student_id='STU001',
            name='Jane Doe',
            email='jane@test.com',
            department='CS',
            semester=3,
        )

    def test_to_dict(self, app):
        with app.app_context():
            s = self._make_student()
            db.session.add(s)
            db.session.commit()
            d = s.to_dict()
            assert d['student_id'] == 'STU001'
            assert d['name'] == 'Jane Doe'
            assert d['email'] == 'jane@test.com'
            assert d['department'] == 'CS'
            assert d['semester'] == 3
            assert d['photo_count'] == 0
            assert d['is_active'] is True
            assert 'id' in d
            assert 'created_at' in d

    def test_full_dict(self, app):
        """Verify to_dict returns all expected fields (full representation)."""
        with app.app_context():
            s = self._make_student()
            db.session.add(s)
            db.session.commit()
            d = s.to_dict()
            expected_keys = {
                'id', 'student_id', 'name', 'email', 'department',
                'semester', 'photo_count', 'is_active', 'created_at', 'updated_at'
            }
            assert set(d.keys()) == expected_keys


# ---------------------------------------------------------------------------
# AttendanceRecord model
# ---------------------------------------------------------------------------

class TestAttendanceRecordModel:
    def _make_record(self, session_id=None):
        return AttendanceRecord(
            student_id=1,
            session_id=session_id,
            date=date.today(),
            time_in=datetime.now(timezone.utc),
            status='present',
            confidence=0.92,
            method='face',
            liveness_score=0.88,
            notes='Test note',
        )

    def test_to_dict(self, app):
        with app.app_context():
            rec = self._make_record()
            db.session.add(rec)
            db.session.commit()
            d = rec.to_dict()
            assert d['status'] == 'present'
            assert d['confidence'] == 0.92
            assert d['method'] == 'face'
            assert d['notes'] == 'Test note'
            assert 'date' in d
            assert 'time_in' in d

    def test_to_dict_with_student(self, app):
        with app.app_context():
            student = Student(student_id='S100', name='Record Student')
            db.session.add(student)
            db.session.commit()
            rec = AttendanceRecord(
                student_id=student.id,
                date=date.today(),
                time_in=datetime.now(timezone.utc),
                status='present',
            )
            db.session.add(rec)
            db.session.commit()
            d = rec.to_dict_with_student()
            assert d['name'] == 'Record Student'
            assert d['sid'] == 'S100'


# ---------------------------------------------------------------------------
# AttendanceSession model
# ---------------------------------------------------------------------------

class TestAttendanceSessionModel:
    def test_to_dict(self, app):
        with app.app_context():
            user = User(username='sessuser', role='teacher')
            user.set_password('Pass1234')
            db.session.add(user)
            db.session.commit()
            session = AttendanceSession(
                started_by=user.id,
                tolerance=0.6,
                status='active',
            )
            db.session.add(session)
            db.session.commit()
            d = session.to_dict()
            assert d['started_by'] == user.id
            assert d['status'] == 'active'
            assert d['tolerance'] == 0.6
            assert d['record_count'] == 0
            assert d['ended_at'] is None


# ---------------------------------------------------------------------------
# Schedule model
# ---------------------------------------------------------------------------

class TestScheduleModel:
    def test_days_list_getter(self, app):
        with app.app_context():
            s = Schedule(
                name='Test', days_of_week='0,1,2,3',
                start_time='09:00', end_time='10:00',
            )
            assert s.days_list == [0, 1, 2, 3]

    def test_days_list_getter_empty(self, app):
        with app.app_context():
            s = Schedule(
                name='Test', days_of_week='',
                start_time='09:00', end_time='10:00',
            )
            assert s.days_list == []

    def test_days_list_getter_none(self, app):
        with app.app_context():
            s = Schedule(
                name='Test', days_of_week=None,
                start_time='09:00', end_time='10:00',
            )
            s.days_of_week = None
            assert s.days_list == []

    def test_days_list_setter(self, app):
        with app.app_context():
            s = Schedule(
                name='Test', days_of_week='',
                start_time='09:00', end_time='10:00',
            )
            s.days_list = [1, 3, 5]
            assert s.days_of_week == '1,3,5'

    def test_days_list_filters_invalid(self, app):
        with app.app_context():
            s = Schedule(
                name='Test', days_of_week='0,7,-1,3',
                start_time='09:00', end_time='10:00',
            )
            assert s.days_list == [0, 3]

    def test_to_dict(self, app):
        with app.app_context():
            s = Schedule(
                name='Morning', department='CS',
                days_of_week='0,1,2', start_time='09:00',
                end_time='10:00', late_threshold=15,
                grace_period=5,
            )
            db.session.add(s)
            db.session.commit()
            d = s.to_dict()
            assert d['name'] == 'Morning'
            assert d['department'] == 'CS'
            assert d['days_of_week'] == [0, 1, 2]
            assert d['late_threshold'] == 15
            assert d['grace_period'] == 5
            assert d['is_active'] is True


# ---------------------------------------------------------------------------
# AuditLog model
# ---------------------------------------------------------------------------

class TestAuditLogModel:
    def test_to_dict_json_details(self, app):
        with app.app_context():
            user = User(username='audituser', role='admin')
            user.set_password('Pass1234')
            db.session.add(user)
            db.session.commit()
            log = AuditLog(
                user_id=user.id,
                action='create',
                entity_type='student',
                entity_id=42,
                details=json.dumps({'key': 'value'}),
                ip_address='127.0.0.1',
            )
            db.session.add(log)
            db.session.commit()
            d = log.to_dict()
            assert d['action'] == 'create'
            assert d['entity_type'] == 'student'
            assert d['entity_id'] == 42
            assert d['details'] == {'key': 'value'}
            assert d['username'] == 'audituser'
            assert d['ip_address'] == '127.0.0.1'

    def test_to_dict_plain_text_details(self, app):
        with app.app_context():
            log = AuditLog(
                user_id=None,
                action='delete',
                entity_type='student',
                details='Deleted: John Doe',
            )
            db.session.add(log)
            db.session.commit()
            d = log.to_dict()
            assert d['details'] == 'Deleted: John Doe'
            assert d['username'] is None

    def test_to_dict_no_details(self, app):
        with app.app_context():
            log = AuditLog(
                action='login',
                entity_type='user',
            )
            db.session.add(log)
            db.session.commit()
            d = log.to_dict()
            assert d['details'] is None


# ---------------------------------------------------------------------------
# FaceEncoding model
# ---------------------------------------------------------------------------

class TestFaceEncodingModel:
    def test_to_dict(self, app):
        with app.app_context():
            student = Student(student_id='FE001', name='Face Student')
            db.session.add(student)
            db.session.commit()
            enc = FaceEncoding(
                student_id=student.id,
                encoding_blob=b'\x00' * 512,
                photo_path='/some/path/photo_1.jpg',
            )
            db.session.add(enc)
            db.session.commit()
            d = enc.to_dict()
            assert d['student_id'] == student.id
            assert d['photo_path'] == '/some/path/photo_1.jpg'
            assert 'id' in d
            assert 'created_at' in d
            assert 'encoding_blob' not in d
