"""Service-layer unit tests."""

import os
import csv
import io
import tempfile
from datetime import date, timedelta


from app.extensions import db
from app.models.user import User
from app.models.student import Student
from app.models.schedule import Schedule


# ---------------------------------------------------------------------------
# Attendance service
# ---------------------------------------------------------------------------

class TestAttendanceService:
    def _seed_student(self):
        s = Student(student_id='SV001', name='Svc Student', department='CS')
        db.session.add(s)
        db.session.commit()
        return s

    def _seed_user(self):
        u = User(username='svcuser', role='teacher')
        u.set_password('pass1234')
        db.session.add(u)
        db.session.commit()
        return u

    def test_start_session(self, app):
        from app.services.attendance import start_session
        user = self._seed_user()
        with app.app_context():
            session = start_session(user_id=user.id)
            assert session.status == 'active'
            assert session.started_by == user.id

    def test_get_active_session_none(self, app):
        from app.services.attendance import get_active_session
        with app.app_context():
            assert get_active_session() is None

    def test_get_active_session_exists(self, app):
        from app.services.attendance import start_session, get_active_session
        user = self._seed_user()
        with app.app_context():
            start_session(user_id=user.id)
            active = get_active_session()
            assert active is not None
            assert active.status == 'active'

    def test_stop_session(self, app):
        from app.services.attendance import start_session, stop_session
        user = self._seed_user()
        with app.app_context():
            session = start_session(user_id=user.id)
            stopped = stop_session(session.id)
            assert stopped.status == 'ended'
            assert stopped.ended_at is not None

    def test_stop_nonexistent_session(self, app):
        from app.services.attendance import stop_session
        with app.app_context():
            result = stop_session(99999)
            assert result is None

    def test_mark_attendance(self, app):
        from app.services.attendance import start_session, mark_attendance
        user = self._seed_user()
        student = self._seed_student()
        with app.app_context():
            session = start_session(user_id=user.id)
            result = mark_attendance(
                student_db_id=student.id,
                session_id=session.id,
                confidence=0.95,
            )
            assert result['status'] == 'marked'

    def test_mark_attendance_already_marked(self, app):
        from app.services.attendance import start_session, mark_attendance
        user = self._seed_user()
        student = self._seed_student()
        with app.app_context():
            session = start_session(user_id=user.id)
            mark_attendance(student_db_id=student.id, session_id=session.id, confidence=0.9)
            result = mark_attendance(student_db_id=student.id, session_id=session.id, confidence=0.9)
            assert result['status'] == 'already_marked'

    def test_mark_attendance_no_active_session(self, app):
        from app.services.attendance import mark_attendance
        with app.app_context():
            result = mark_attendance(student_db_id=1, session_id=99999, confidence=0.9)
            assert 'error' in result

    def test_mark_manual(self, app):
        from app.services.attendance import mark_manual
        student = self._seed_student()
        with app.app_context():
            result = mark_manual(student_db_id=student.id)
            assert result['status'] == 'marked'

    def test_mark_manual_duplicate(self, app):
        from app.services.attendance import mark_manual
        student = self._seed_student()
        with app.app_context():
            mark_manual(student_db_id=student.id)
            result = mark_manual(student_db_id=student.id)
            assert 'error' in result

    def test_get_today_attendance_empty(self, app):
        from app.services.attendance import get_today_attendance
        with app.app_context():
            result = get_today_attendance()
            assert result == []

    def test_get_today_attendance_with_records(self, app):
        from app.services.attendance import mark_manual, get_today_attendance
        student = self._seed_student()
        with app.app_context():
            mark_manual(student_db_id=student.id)
            result = get_today_attendance()
            assert len(result) == 1
            assert result[0]['name'] == 'Svc Student'

    def test_get_today_stats_empty(self, app):
        from app.services.attendance import get_today_stats
        with app.app_context():
            stats = get_today_stats()
            assert stats['total_students'] == 0
            assert stats['present'] == 0
            assert stats['rate'] == 0

    def test_get_today_stats_with_data(self, app):
        from app.services.attendance import mark_manual, get_today_stats
        student = self._seed_student()
        with app.app_context():
            mark_manual(student_db_id=student.id)
            stats = get_today_stats()
            assert stats['total_students'] == 1
            assert stats['present'] >= 0
            assert stats['total_marked'] >= 1

    def test_get_attendance_range(self, app):
        from app.services.attendance import mark_manual, get_attendance_range
        student = self._seed_student()
        with app.app_context():
            mark_manual(student_db_id=student.id)
            today = date.today()
            result = get_attendance_range(today, today)
            assert len(result) == 1

    def test_get_attendance_range_filtered(self, app):
        from app.services.attendance import mark_manual, get_attendance_range
        student = self._seed_student()
        with app.app_context():
            mark_manual(student_db_id=student.id)
            today = date.today()
            result = get_attendance_range(today, today, student_db_id=student.id)
            assert len(result) == 1
            # Filter by nonexistent student
            result2 = get_attendance_range(today, today, student_db_id=99999)
            assert len(result2) == 0

    def test_get_attendance_range_empty(self, app):
        from app.services.attendance import get_attendance_range
        with app.app_context():
            today = date.today()
            old = today - timedelta(days=30)
            result = get_attendance_range(old, old)
            assert result == []


# ---------------------------------------------------------------------------
# Storage service
# ---------------------------------------------------------------------------

class TestStorageService:
    def test_ensure_dir(self, app):
        from app.services.storage import StorageService
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = StorageService(tmpdir)
            path = svc.ensure_dir('student1')
            assert os.path.isdir(path)

    def test_save_image(self, app):
        from app.services.storage import StorageService
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = StorageService(tmpdir)
            filepath = svc.save_image('student1', 'photo.jpg', b'fake-image-data')
            assert os.path.isfile(filepath)
            with open(filepath, 'rb') as f:
                assert f.read() == b'fake-image-data'

    def test_delete_student_dir(self, app):
        from app.services.storage import StorageService
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = StorageService(tmpdir)
            svc.save_image('student1', 'photo.jpg', b'data')
            result = svc.delete_student_dir('student1')
            assert result is True
            assert not os.path.isdir(os.path.join(tmpdir, 'student1'))

    def test_delete_student_dir_nonexistent(self, app):
        from app.services.storage import StorageService
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = StorageService(tmpdir)
            result = svc.delete_student_dir('nonexistent')
            assert result is False

    def test_list_student_files(self, app):
        from app.services.storage import StorageService
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = StorageService(tmpdir)
            svc.save_image('s1', 'a.jpg', b'x')
            svc.save_image('s1', 'b.jpg', b'y')
            files = svc.list_student_files('s1')
            assert len(files) == 2

    def test_list_student_files_empty(self, app):
        from app.services.storage import StorageService
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = StorageService(tmpdir)
            files = svc.list_student_files('nobody')
            assert files == []


# ---------------------------------------------------------------------------
# Export service
# ---------------------------------------------------------------------------

class TestExportService:
    def test_generate_csv(self, app):
        from app.services.export import generate_csv
        records = [
            {
                'sid': 'S001', 'name': 'Alice', 'department': 'CS',
                'date': '2025-01-15', 'time_in': '09:00', 'time_out': '',
                'status': 'present', 'confidence': 0.95,
                'method': 'face', 'liveness_score': 0.9,
            },
            {
                'sid': 'S002', 'name': 'Bob', 'department': 'Math',
                'date': '2025-01-15', 'time_in': '09:05', 'time_out': '',
                'status': 'late', 'confidence': 0.88,
                'method': 'manual', 'liveness_score': '',
            },
        ]
        csv_str = generate_csv(records)
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)
        assert len(rows) == 3  # header + 2 data rows
        assert rows[0][0] == 'Student ID'
        assert rows[1][0] == 'S001'
        assert rows[2][0] == 'S002'

    def test_generate_csv_empty(self, app):
        from app.services.export import generate_csv
        csv_str = generate_csv([])
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)
        assert len(rows) == 1  # header only


# ---------------------------------------------------------------------------
# Seed service
# ---------------------------------------------------------------------------

class TestSeedService:
    def test_seed_defaults_creates_users_and_schedules(self, app):
        from app.services.seed import seed_defaults
        with app.app_context():
            seed_defaults()
            assert User.query.filter_by(username='admin').first() is not None
            assert User.query.filter_by(username='teacher').first() is not None
            assert Schedule.query.count() >= 2

    def test_seed_defaults_idempotent(self, app):
        from app.services.seed import seed_defaults
        with app.app_context():
            seed_defaults()
            seed_defaults()
            # Should not create duplicates
            assert User.query.filter_by(username='admin').count() == 1
            assert User.query.filter_by(username='teacher').count() == 1


# ---------------------------------------------------------------------------
# Hardware service
# ---------------------------------------------------------------------------

class TestHardwareService:
    def test_get_hardware_profile(self, app):
        from app.services.hardware import get_hardware_profile
        # Reset singleton for test
        import app.services.hardware as hw
        hw._profile = None
        with app.app_context():
            profile = get_hardware_profile()
            assert profile.cpu_cores >= 1
            assert profile.ram_gb > 0
            assert profile.platform in ('linux', 'darwin', 'windows')
            assert profile.tier() in ('high_gpu', 'mid_gpu', 'igpu', 'high_cpu', 'mid_cpu', 'low')

    def test_hardware_profile_to_dict(self, app):
        from app.services.hardware import get_hardware_profile
        import app.services.hardware as hw
        hw._profile = None
        with app.app_context():
            profile = get_hardware_profile()
            d = profile.to_dict()
            assert 'cpu_cores' in d
            assert 'gpu_type' in d
            assert 'tier' in d

    def test_hardware_optimal_config(self, app):
        from app.services.hardware import get_hardware_profile
        import app.services.hardware as hw
        hw._profile = None
        with app.app_context():
            profile = get_hardware_profile()
            cfg = profile.optimal_config()
            assert 'face_det_size' in cfg
            assert 'batch_size' in cfg
            assert 'providers' in cfg
            assert cfg['tier'] == profile.tier()
