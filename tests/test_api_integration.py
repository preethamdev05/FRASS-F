"""Comprehensive API integration tests."""



# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_health_returns_200(self, client):
        resp = client.get('/api/health')
        assert resp.status_code == 200

    def test_health_body(self, client):
        resp = client.get('/api/health')
        data = resp.json
        assert data['status'] in ('healthy', 'degraded')
        assert 'checks' in data
        assert 'version' in data

    def test_health_db_ok(self, client):
        resp = client.get('/api/health')
        assert resp.json['checks']['database'] == 'ok'


# ---------------------------------------------------------------------------
# Login flow
# ---------------------------------------------------------------------------

class TestLoginFlow:
    def test_login_success(self, client, auth_client):
        """auth_client already logged in; verify we can also login fresh."""
        resp = client.post('/api/auth/login', json={
            'username': 'testadmin', 'password': 'testpass'
        })
        assert resp.status_code == 200
        assert resp.json['user']['username'] == 'testadmin'

    def test_login_wrong_password(self, client, auth_client):
        resp = client.post('/api/auth/login', json={
            'username': 'testadmin', 'password': 'wrongpass'
        })
        assert resp.status_code == 401

    def test_login_null_username(self, client):
        resp = client.post('/api/auth/login', json={
            'username': None, 'password': 'whatever'
        })
        assert resp.status_code == 400

    def test_login_null_password(self, client):
        resp = client.post('/api/auth/login', json={
            'username': 'someone', 'password': None
        })
        assert resp.status_code == 400

    def test_login_empty_body(self, client):
        resp = client.post('/api/auth/login', json={})
        assert resp.status_code == 400

    def test_login_no_json(self, client):
        resp = client.post('/api/auth/login')
        assert resp.status_code in (400, 415)


# ---------------------------------------------------------------------------
# MFA setup
# ---------------------------------------------------------------------------

class TestMFASetup:
    def test_mfa_setup_returns_secret_and_qr(self, auth_client):
        resp = auth_client.post('/api/auth/mfa/setup')
        assert resp.status_code == 200
        data = resp.json
        assert 'secret' in data
        assert 'qr_code' in data
        assert data['qr_code'].startswith('data:image/png;base64,')

    def test_mfa_setup_requires_auth(self, client):
        resp = client.post('/api/auth/mfa/setup')
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Register user
# ---------------------------------------------------------------------------

class TestRegisterUser:
    def test_register_success(self, auth_client):
        resp = auth_client.post('/api/auth/register', json={
            'username': 'newuser',
            'password': 'StrongPass1',
            'role': 'teacher',
        })
        assert resp.status_code == 201
        assert resp.json['username'] == 'newuser'

    def test_register_duplicate(self, auth_client):
        auth_client.post('/api/auth/register', json={
            'username': 'dupuser', 'password': 'StrongPass1'
        })
        resp = auth_client.post('/api/auth/register', json={
            'username': 'dupuser', 'password': 'StrongPass1'
        })
        assert resp.status_code == 409

    def test_register_weak_password(self, auth_client):
        resp = auth_client.post('/api/auth/register', json={
            'username': 'weakuser', 'password': 'short'
        })
        assert resp.status_code == 400

    def test_register_missing_username(self, auth_client):
        resp = auth_client.post('/api/auth/register', json={
            'password': 'StrongPass1'
        })
        assert resp.status_code == 400

    def test_register_invalid_role(self, auth_client):
        resp = auth_client.post('/api/auth/register', json={
            'username': 'badrole', 'password': 'StrongPass1', 'role': 'superadmin'
        })
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------

class TestChangePassword:
    def test_change_password_success(self, auth_client):
        resp = auth_client.post('/api/auth/change-password', json={
            'old_password': 'testpass',
            'new_password': 'NewStrong1',
        })
        assert resp.status_code == 200

    def test_change_password_wrong_old(self, auth_client):
        resp = auth_client.post('/api/auth/change-password', json={
            'old_password': 'wrongold',
            'new_password': 'NewStrong1',
        })
        assert resp.status_code == 400

    def test_change_password_weak_new(self, auth_client):
        resp = auth_client.post('/api/auth/change-password', json={
            'old_password': 'testpass',
            'new_password': 'weak',
        })
        assert resp.status_code == 400

    def test_change_password_null_body(self, auth_client):
        resp = auth_client.post('/api/auth/change-password', json={})
        assert resp.status_code == 400

    def test_change_password_requires_auth(self, client):
        resp = client.post('/api/auth/change-password', json={
            'old_password': 'a', 'new_password': 'NewStrong1'
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Student CRUD
# ---------------------------------------------------------------------------

class TestStudentCRUD:
    def _create(self, auth_client, **overrides):
        payload = {'student_id': 'S001', 'name': 'Alice'}
        payload.update(overrides)
        return auth_client.post('/api/students', json=payload)

    def test_create_student(self, auth_client):
        resp = self._create(auth_client)
        assert resp.status_code == 201
        assert resp.json['name'] == 'Alice'

    def test_list_students(self, auth_client):
        self._create(auth_client, student_id='S1')
        self._create(auth_client, student_id='S2')
        resp = auth_client.get('/api/students')
        assert resp.status_code == 200
        assert len(resp.json) == 2

    def test_get_student(self, auth_client):
        create_resp = self._create(auth_client)
        sid = create_resp.json['id']
        resp = auth_client.get(f'/api/students/{sid}')
        assert resp.status_code == 200
        assert resp.json['student_id'] == 'S001'

    def test_get_student_not_found(self, auth_client):
        resp = auth_client.get('/api/students/9999')
        assert resp.status_code == 404

    def test_update_student(self, auth_client):
        create_resp = self._create(auth_client)
        sid = create_resp.json['id']
        resp = auth_client.put(f'/api/students/{sid}', json={'name': 'Bob'})
        assert resp.status_code == 200
        assert resp.json['name'] == 'Bob'

    def test_update_student_not_found(self, auth_client):
        resp = auth_client.put('/api/students/9999', json={'name': 'X'})
        assert resp.status_code == 404

    def test_delete_student(self, auth_client):
        create_resp = self._create(auth_client)
        sid = create_resp.json['id']
        resp = auth_client.delete(f'/api/students/{sid}')
        assert resp.status_code == 200
        assert resp.json['status'] == 'deleted'
        # Verify gone
        assert auth_client.get(f'/api/students/{sid}').status_code == 404

    def test_delete_student_not_found(self, auth_client):
        resp = auth_client.delete('/api/students/9999')
        assert resp.status_code == 404

    def test_create_student_no_data(self, auth_client):
        resp = auth_client.post('/api/students', json={})
        assert resp.status_code == 400

    def test_create_duplicate_student(self, auth_client):
        self._create(auth_client, student_id='DUP')
        resp = self._create(auth_client, student_id='DUP')
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Schedule CRUD
# ---------------------------------------------------------------------------

class TestScheduleCRUD:
    def _create(self, auth_client, **overrides):
        payload = {
            'name': 'Morning',
            'start_time': '09:00',
            'end_time': '10:00',
            'days_of_week': [0, 1, 2],
        }
        payload.update(overrides)
        return auth_client.post('/api/schedules', json=payload)

    def test_create_schedule(self, auth_client):
        resp = self._create(auth_client)
        assert resp.status_code == 201
        assert resp.json['name'] == 'Morning'

    def test_list_schedules(self, auth_client):
        self._create(auth_client)
        resp = auth_client.get('/api/schedules')
        assert resp.status_code == 200
        assert len(resp.json) >= 1

    def test_update_schedule(self, auth_client):
        create_resp = self._create(auth_client)
        sid = create_resp.json['id']
        resp = auth_client.put(f'/api/schedules/{sid}', json={'name': 'Afternoon'})
        assert resp.status_code == 200
        assert resp.json['name'] == 'Afternoon'

    def test_update_schedule_not_found(self, auth_client):
        resp = auth_client.put('/api/schedules/9999', json={'name': 'X'})
        assert resp.status_code == 404

    def test_delete_schedule(self, auth_client):
        create_resp = self._create(auth_client)
        sid = create_resp.json['id']
        resp = auth_client.delete(f'/api/schedules/{sid}')
        assert resp.status_code == 200

    def test_delete_schedule_not_found(self, auth_client):
        resp = auth_client.delete('/api/schedules/9999')
        assert resp.status_code == 404

    def test_create_schedule_no_data(self, auth_client):
        resp = auth_client.post('/api/schedules', json={})
        assert resp.status_code == 400

    def test_create_schedule_bad_time(self, auth_client):
        resp = self._create(auth_client, start_time='25:99')
        assert resp.status_code == 400

    def test_update_schedule_bad_time(self, auth_client):
        create_resp = self._create(auth_client)
        sid = create_resp.json['id']
        resp = auth_client.put(f'/api/schedules/{sid}', json={'end_time': 'bad'})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

class TestAttendance:
    def _setup_student(self, auth_client):
        resp = auth_client.post('/api/students', json={
            'student_id': 'A001', 'name': 'Att Student'
        })
        return resp.json['id']

    def test_start_session(self, auth_client):
        self._setup_student(auth_client)
        resp = auth_client.post('/api/attendance/start', json={})
        assert resp.status_code == 200
        assert 'session_id' in resp.json

    def test_stop_session(self, auth_client):
        auth_client.post('/api/attendance/start', json={})
        resp = auth_client.post('/api/attendance/stop', json={})
        assert resp.status_code == 200
        assert resp.json['status'] == 'stopped'

    def test_mark_manual(self, auth_client):
        sid = self._setup_student(auth_client)
        resp = auth_client.post('/api/attendance/mark-manual', json={
            'student_id': sid
        })
        assert resp.status_code == 200
        assert resp.json['status'] == 'marked'

    def test_mark_manual_missing_student(self, auth_client):
        resp = auth_client.post('/api/attendance/mark-manual', json={})
        assert resp.status_code == 400

    def test_get_today(self, auth_client):
        resp = auth_client.get('/api/attendance/today')
        assert resp.status_code == 200
        assert isinstance(resp.json, list)

    def test_get_stats(self, auth_client):
        resp = auth_client.get('/api/attendance/stats')
        assert resp.status_code == 200
        data = resp.json
        assert 'total_students' in data
        assert 'present' in data
        assert 'rate' in data

    def test_get_session_info(self, auth_client):
        resp = auth_client.get('/api/attendance/session')
        assert resp.status_code == 200
        assert 'active' in resp.json

    def test_attendance_range(self, auth_client):
        from datetime import date
        today = date.today().isoformat()
        resp = auth_client.get(f'/api/attendance/range?start={today}&end={today}')
        assert resp.status_code == 200

    def test_attendance_range_bad_date(self, auth_client):
        resp = auth_client.get('/api/attendance/range?start=not-a-date&end=also-bad')
        assert resp.status_code == 400

    def test_dashboard(self, auth_client):
        resp = auth_client.get('/api/attendance/dashboard')
        assert resp.status_code == 200
        data = resp.json
        assert 'total_students' in data
        assert 'week_trend' in data

    def test_mark_manual_duplicate(self, auth_client):
        sid = self._setup_student(auth_client)
        auth_client.post('/api/attendance/mark-manual', json={'student_id': sid})
        resp = auth_client.post('/api/attendance/mark-manual', json={'student_id': sid})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

class TestReports:
    def test_export_csv(self, auth_client):
        from datetime import date
        today = date.today().isoformat()
        resp = auth_client.get(f'/api/reports/export/csv?start={today}&end={today}')
        assert resp.status_code == 200
        assert resp.content_type == 'text/csv; charset=utf-8'

    def test_export_csv_bad_date(self, auth_client):
        resp = auth_client.get('/api/reports/export/csv?start=bad&end=bad')
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

class TestAdmin:
    def test_list_users(self, auth_client):
        resp = auth_client.get('/api/admin/users')
        assert resp.status_code == 200
        assert isinstance(resp.json, list)
        assert any(u['username'] == 'testadmin' for u in resp.json)

    def test_audit_log(self, auth_client):
        resp = auth_client.get('/api/admin/audit')
        assert resp.status_code == 200
        data = resp.json
        assert 'total' in data
        assert 'entries' in data

    def test_audit_log_pagination(self, auth_client):
        resp = auth_client.get('/api/admin/audit?page=1&per_page=5')
        assert resp.status_code == 200

    def test_hardware_info(self, auth_client):
        resp = auth_client.get('/api/admin/hardware')
        assert resp.status_code == 200
        data = resp.json
        assert 'cpu_cores' in data
        assert 'platform' in data

    def test_admin_requires_auth(self, client):
        resp = client.get('/api/admin/users')
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# WebSocket connection
# ---------------------------------------------------------------------------

class TestWebSocket:
    def test_socketio_connect(self, app):
        """Test that the SocketIO test client can connect."""
        from app.extensions import socketio
        test_client = socketio.test_client(app)
        assert test_client.is_connected()
        test_client.disconnect()


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------

class TestSecurityHeaders:
    def test_security_headers_present(self, client):
        resp = client.get('/api/health')
        headers = resp.headers
        assert headers.get('X-Content-Type-Options') == 'nosniff'
        assert headers.get('X-Frame-Options') == 'DENY'
        assert headers.get('X-XSS-Protection') == '1; mode=block'
        assert headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'
        assert 'camera' in headers.get('Permissions-Policy', '')
